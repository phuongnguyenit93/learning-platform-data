# `issuer-uri` and Validating the `iss` Claim Against the Configured Value

## 1. The Resource Server Must Know Who Issues Access Tokens

An Orders API built with **Spring Boot and Spring Security OAuth 2.0 Resource Server** typically receives JWT access tokens:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

The API cannot treat every structurally valid JWT as trustworthy. It needs to determine **which Authorization Server is allowed to issue tokens for the API**. In a JWT, the **`iss`** (issuer) claim describes the issuing party; in Spring Security configuration, **`issuer-uri`** sets the issuer value that the Resource Server trusts.

Suppose the Authorization Server has the issuer:

~~~text
https://id.example.test/realms/shop
~~~

A valid access token per contract may carry:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

This is JSON illustrating the payload, **not a real signed JWT**. The goal of validating `iss` is to ensure that **after cryptographic verification**, the token declares the exact issuer configured by the API.

In Spring Boot, the typical minimal configuration is:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

**Key point:** `issuer-uri` is a **trusted value preconfigured by the application**, used to discover metadata/public keys (when discovery is chosen) and to **compare against the `iss` claim in the JWT**. It is not an arbitrary URI extracted from a token and automatically trusted.

## 2. Issuer, Client, Audience, and JWKS Have Different Roles

In OAuth 2.0/OIDC, addresses and identifiers often appear together, but they answer different questions:

| Value | Example | Question answered |
|---|---|---|
| **Issuer / `iss`** | `https://id.example.test/realms/shop` | Who issued the token? |
| **Audience / `aud`** | `orders-api` | Which API/resource is the token intended for? |
| **Client ID** | `shop-web` | Which client application receives/is granted authorization? |
| **JWKS URI** | `https://id.example.test/realms/shop/protocol/openid-connect/certs` | Where are the published public keys fetched from? |
| **Authorization endpoint** | `.../protocol/openid-connect/auth` | Where does the client send the user to request authorization? |
| **Token endpoint** | `.../protocol/openid-connect/token` | Where does the client exchange a code or grant for a token? |
| **Resource Server** | `https://api.example.test` | Which API hosts the protected resources? |

Endpoints with `/protocol/openid-connect/...` paths in the table are just **one illustrative layout used by certain Identity Providers**, not a fixed standard endpoint path across all providers.

A JWT with:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": "orders-api"
}
~~~

may have both the right issuer and the right audience; another JWT with:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": "billing-api"
}
~~~

still has the same issuer, yet **is not intended for the Orders API**.

Therefore, **issuer validation and audience validation complement each other**:

- `iss` identifies the trusted **issuing source**.
- `aud` identifies the **intended recipient** of the token.
- `exp` and `nbf` define the **time window** during which the token is valid.
- Signature/JWS verifies that the token contents have not been tampered with and were signed with a policy-compliant key.
- `scope` or authorities determine **endpoint permissions**; resource ownership must also be checked at the business layer.

Checking only `iss` will not prevent an access token meant for another service from being sent mistakenly to the Orders API if both services trust the same issuer. Checking only the signature also does not replace an issuer validator when multiple issuers may be tied to shared key sets or shared infrastructure.

## 3. How Is the `iss` Claim in a JWT Compared?

### 3.1. The Issuer Value Is an Identifier, Not Just a Domain

According to RFC 7519, `iss` is a `StringOrURI` value identifying the issuing party. In an OAuth/OIDC system, it is usually an HTTPS URI.

Suppose the API configures:

~~~text
spring.security.oauth2.resourceserver.jwt.issuer-uri =
https://id.example.test/realms/shop
~~~

Test payloads:

| JWT claim `iss` | Compared to config | Meaning |
|---|---|---|
| `https://id.example.test/realms/shop` | Match | Matches expected issuer |
| `https://id.example.test/realms/other` | Mismatch | Different realm/tenant |
| `https://id.example.test/realms/shop/` | Mismatch | Different trailing slash |
| `http://id.example.test/realms/shop` | Mismatch | Different scheme |
| `https://another.example.test/realms/shop` | Mismatch | Different host |
| `https://id.example.test` | Mismatch | Missing issuer path |
| Missing `iss` | Fails issuer requirement | Missing claim requiring verification |
| `"iss": 123` | Wrong type per contract | Not an issuer String |

**Do not strip trailing slashes, drop paths, change schemes, or loosely compare domains** to accept tokens. Those URI values can refer to different issuers even though they look nearly identical.

Spring Security uses an issuer validator matching the configured expected value. When the `iss` claim does not match, the JWT fails validation and the request must be rejected. In a typical JWT Resource Server, that is **401 Unauthorized** for an invalid Bearer token.

### 3.2. A Valid Signature Does Not Mean the Issuer Is Right

Suppose there are two issuers in the same organization:

~~~text
Issuer A: https://id.example.test/realms/retail
Issuer B: https://id.example.test/realms/partners
~~~

If the API trusts only **Issuer A**, a token issued by Issuer B must still be rejected **even if**, due to misconfiguration or shared infrastructure, its signature verifies under a key in the key set trusted by the API.

The trust rule is not:

~~~text
Signature verifies -> allow
~~~

Instead, at a minimum:

~~~text
Right key source and allowed algorithm
  + valid signature
  + iss == configured issuer
  + valid exp/nbf
  + aud matches API
  + matching token profile
  + endpoint/resource permissions
  -> only then allowed to process request
~~~

Likewise, the `iss` claim is a string inside **untrusted input data until the token is verified**. Never trust the `iss` content on its own just because it appears in a three-part Base64URL JWT.

## 4. What Is Discovery and How Does It Relate to `issuer-uri`?

**Discovery** allows a Resource Server to look up the Authorization Server/OpenID Provider configuration from a **trusted issuer**. Rather than developers hardcoding every endpoint, the application can retrieve metadata published by the provider.

Two common specification families:

- **OpenID Connect Discovery**: OpenID Provider Configuration.
- **OAuth 2.0 Authorization Server Metadata** (RFC 8414): metadata for Authorization Servers.

What they share: providing issuer identity information and related endpoints, especially **`jwks_uri`** for verifying JWT signatures.

### 4.1. Sample Metadata

With issuer:

~~~text
https://id.example.test/realms/shop
~~~

a provider may publish metadata like:

~~~text
https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

Abbreviated sample contents:

~~~json
{
  "issuer": "https://id.example.test/realms/shop",
  "authorization_endpoint":
    "https://id.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint":
    "https://id.example.test/realms/shop/protocol/openid-connect/token",
  "jwks_uri":
    "https://id.example.test/realms/shop/protocol/openid-connect/certs"
}
~~~

This is JSON **illustrating metadata**. Actual endpoints must be confirmed against the provider. Aside from the OIDC Discovery path formed as issuer + `/.well-known/openid-configuration`, OAuth metadata can use `/.well-known/oauth-authorization-server` combined with the issuer path; Spring Security supports the corresponding metadata locations listed in current documentation.

**Do not infer the JWKS URI by appending a fixed suffix to the issuer.** JWKS addresses do not have a mandatory uniform path structure across all providers; obtain them from metadata or the provider contract.

### 4.2. Discovery Does Not Mean OIDC Login

A Resource Server only needs to verify **access tokens**. Using OIDC Provider Configuration to find public keys **does not turn it into an OIDC Login Client**.

Roles:

| Spring Security capability | Purpose |
|---|---|
| `oauth2ResourceServer().jwt()` | Verifies Bearer JWT access tokens to protect APIs |
| `oauth2Login()` | Performs OAuth 2.0/OIDC user login for a web client application |
| `oauth2Client()` | Manages `OAuth2AuthorizedClient` to call other services |

A Resource Server can consume metadata from an OpenID Provider, but **that does not mean it should accept an ID Token instead of an access token**. An OIDC ID Token is issued to the client; the API needs a JWT access token with the right audience/token type.

### 4.3. Metadata Must Be Consistent with the Trusted Issuer

In the example system, three values must align:

~~~text
Configured issuer-uri:
https://id.example.test/realms/shop

Metadata "issuer":
https://id.example.test/realms/shop

JWT claim "iss":
https://id.example.test/realms/shop
~~~

If the metadata reports a different issuer, or tokens are issued with an `iss` differing from configuration, that is a **configuration/contract error to resolve**, not a reason to remove issuer validation.

For example, if the issuer sits behind a reverse proxy: metadata returns `issuer = http://idp-internal:8080/realms/shop`, while the token has `iss = https://login.example.com/realms/shop`. The Resource Server should standardize on the official public issuer with the provider and configure metadata/forwarded headers properly, rather than arbitrarily accepting both issuers.

## 5. Minimal Spring Boot `issuer-uri` Configuration

### 5.1. Dependencies

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The OAuth2 Resource Server starter brings in the Spring Security integration, including corresponding JOSE/JWT support in Spring Boot's dependency setup. If managing dependencies directly with Spring Security modules instead of the starter, ensure both the resource server and JOSE components are present for JWT verification.

### 5.2. `application.yml` Configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

This configuration alone suffices for the basic scenario when:

1. The Authorization Server supports compatible metadata discovery.
2. JWKS publishes the public keys to verify access token signatures.
3. The JWT uses a profile and signing algorithm supported/accepted by the decoder.
4. The Resource Server can reach the required endpoints at the time keys are resolved.
5. There are no additional policies such as audience or custom claims requiring separate configuration.

Ensure the application actually has a **`SecurityFilterChain` enabling JWT Resource Server**. When Spring Boot auto-configures a suitable chain and the developer has not replaced it, Boot may create a default chain; when supplying a custom chain, you must enable Resource Server in that chain.

### 5.3. Illustrative Filter Chain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

This example scopes the chain to `/api/**`; a real application needs policies protecting any remaining paths. The actual issuer contract is determined by the `issuer-uri` property, while `SecurityFilterChain` selects endpoints and enables Bearer JWT processing.

When receiving a request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

the `BearerTokenAuthenticationFilter` locates the token; `JwtAuthenticationProvider` uses `JwtDecoder` to verify the JWT and validators; if successful, the authentication is stored in `SecurityContext` for authorization rules to evaluate.

### 5.4. What Does the Resource Server Check?

Under a standard `issuer-uri` configuration, Spring Security validates the JWT signature with the appropriate public key and checks foundational claims such as `exp`, `nbf`, and `iss`. Afterward, a converter can map scopes into authorities like `SCOPE_orders.read`.

**Do not infer** that simply configuring `issuer-uri` automatically checks the entire access token contract. `aud`, token type/profile, client, tenant, or business claims may require additional configuration. Applications with strict audience requirements should declare them explicitly.

## 6. Flow: From Issuer to Metadata, JWKS, and `iss` Validation

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant API as Spring Resource Server
    participant Meta as Metadata Endpoint
    participant JWKS as JWKS Endpoint

    Client->>API: GET /api/orders + Bearer JWT
    Note over API: Preconfigured issuer-uri acts as trust anchor
    API->>Meta: Issuer metadata discovery (when needed)
    Meta-->>API: issuer + jwks_uri + metadata
    API->>JWKS: Fetch public signing keys (when needed)
    JWKS-->>API: JWK Set
    API->>API: Verify JWS signature/algorithm
    API->>API: Validate iss == issuer-uri
    API->>API: Validate exp/nbf and other validators
    API->>API: Convert scopes to authorities
    API-->>Client: Allow request to proceed if valid/authorized
~~~

The diagram shows the **relationship between steps**, not that every request calls metadata and JWKS over the network. The library may cache configuration/keys and only reach out again when needed, such as when no matching key is cached or upon key rotation.

### 6.1. When Does Discovery Occur?

This depends on the version and how the decoder is initialized:

- In current Spring Security Servlet documentation, the default Resource Server configuration may use **lazy discovery**, meaning metadata is fetched when handling the first JWT request; `SupplierJwtDecoder` defers initialization.
- In older versions or when the application **manually builds a `JwtDecoder`** using a method that queries the issuer at bean creation time, discovery can occur early during initialization.
- When using `jwk-set-uri` directly alongside `issuer-uri`, the application does not need discovery just to find the JWKS address; however, fetching the actual keys still requires the provider/JWKS endpoint to be available when tokens are validated.

Therefore, avoid absolute rules like “Resource Server always calls the IdP at startup” or “IdP downtime never affects requests”. Rely on the **Spring Security version, decoder initialization method, key cache state, and HTTP client configuration**.

### 6.2. What If Discovery or JWKS Fails?

For example:

- The metadata endpoint is down or lacks a supported discovery path.
- Metadata returns an invalid structure or inconsistent issuer.
- The JWKS endpoint times out or is unreachable.
- The JWT uses a `kid` not yet in cache and the new key cannot be fetched.
- The publisher rotated signing keys, but the Resource Server has not yet retrieved the needed public key.

Without a reliable way to verify, the Resource Server **must not accept tokens based solely on the `iss` claim**. Failures may manifest as authentication failures/401 or infrastructure errors depending on timing/configuration; distinguish invalid tokens from network-induced verification failures.

Operationally, configure appropriate timeouts, monitor discovery/JWKS health, establish clear cache/key-rotation policies, and use HTTPS to access trusted endpoints. Never fall back to accepting unverified JWTs.

## 7. Comparing Three Configurations of `issuer-uri` and `jwk-set-uri`

| Configuration | Discovers JWKS via metadata? | Automatically knows expected `iss`? | When appropriate? |
|---|---|---|---|
| Only `issuer-uri` | Yes, in a compatible discovery pipeline | Yes | Provider supports discovery and uses an agreed issuer |
| `issuer-uri` + `jwk-set-uri` | No need for discovery to locate JWKS | Yes | Want to specify JWKS explicitly and avoid discovery dependency at init |
| Only `jwk-set-uri` | No need for discovery | **No expected issuer by default** | Direct key source available; must configure an issuer validator separately if the API needs to check `iss` |

### 7.1. Only `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Spring Security uses the trusted issuer to resolve metadata, locate public keys, and validate the `iss` claim. The advantages are concise configuration and avoiding hardcoded JWKS endpoints.

### 7.2. `issuer-uri` Combined with `jwk-set-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Each value has a distinct role:

- `issuer-uri` remains the **value that must match the JWT `iss` claim**.
- `jwk-set-uri` is the **address used to fetch public keys to verify JWS signatures**.

This combination fits when you want explicit routing to JWKS while **still preserving issuer validation**.

**Do not assume Spring skips comparing `iss` when `jwk-set-uri` is present**: with both properties in compatible auto-configuration, issuer validation is preserved.

### 7.3. Only `jwk-set-uri`: A Security Trap

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

If no issuer is supplied via another property or a custom validator, the Resource Server **has no configured issuer value to automatically compare `iss` against**. Verifying the JWS signature with a key from JWKS does not prove the token carries an `iss` matching the issuer the API intends to trust.

This matters when:

- A key set is shared or misconfigured across multiple issuers.
- A JWKS endpoint aggregates keys from multiple tenants/realms.
- The API does not want to accept every token signed by the key-holding system across different contexts.

If discovery is unavailable while issuer checking is still needed, prefer **declaring both `issuer-uri` and `jwk-set-uri`**, or properly attach an issuer validator when constructing the decoder manually.

### 7.4. JWKS URI Is Not the `iss` Value

Suppose:

~~~text
issuer-uri:
https://id.example.test/realms/shop

jwk-set-uri:
https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

The JWT must contain:

~~~json
{"iss": "https://id.example.test/realms/shop"}
~~~

The JWT is **not** expected to set `iss` to the `.../certs` URL. This is a very common naming mix-up: **the issuer identifies the publisher**, whereas **JWKS is the endpoint distributing public keys**.

## 8. Validating Issuer and Audience Together

An access token can have the right issuer yet be meant for another application. With Spring Boot supporting the `audiences` property:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

With compatible configuration, the API requires:

~~~text
JWT iss == https://id.example.test/realms/shop
AND
JWT aud contains orders-api
~~~

If a token has:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["billing-api"],
  "exp": 2000000000
}
~~~

then the token has the right issuer but the wrong audience for the Orders API. When an audience validator is active, the request must be rejected.

Conversely:

~~~json
{
  "iss": "https://id.example.test/realms/other",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

then the token has the right audience but the wrong issuer. It must also be rejected.

**Claim checking cannot replace signature verification**: the two payloads above only illustrate data fields. In practice, the JWT must be validly signed, checked for allowed algorithms, and pass time checks before being treated as a trustworthy access token.

## 9. Java Configuration When Creating a Custom `JwtDecoder`

### 9.1. Using `JwtDecoders.fromIssuerLocation`

When using Spring Security outside auto-configuration or wanting to build a decoder explicitly, you can call:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;

String issuer = "https://id.example.test/realms/shop";
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

`JwtDecoders.fromIssuerLocation(issuer)` uses the specified issuer to discover metadata/JWKS and creates a decoder with Spring Security defaults. Calling this method directly during bean creation can cause metadata discovery to happen **at bean creation time**, unlike the lazy path managed by Spring Boot in some versions.

If `issuer-uri` can be used via Spring Boot without needing a custom decoder, it is usually better to let auto-configuration handle this so there are fewer moving parts to maintain.

### 9.2. Using `NimbusJwtDecoder` and Attaching an Explicit Issuer Validator

If you need an explicit JWKS together with an issuer without relying on auto-configured properties, you can declare a bean:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String issuer = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwks = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .build();

        // Keep default validators and require the iss claim to match issuer.
        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

`application.yml` for the bean above:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Explanation:

- `withJwkSetUri(jwks)` creates a decoder using an explicit public key source.
- `JwtValidators.createDefaultWithIssuer(issuer)` adds **issuer validation**, alongside appropriate default validations such as token timestamps.
- `setJwtValidator(...)` sets the validator on the decoder.
- Nothing here automatically configures Orders API-specific audience/role/tenant rules.

When you supply your own `JwtDecoder` bean, **Spring Boot may back off from creating its auto-configured decoder**. Convenient auto-configuration properties, including `audiences`, should not be assumed to apply to your custom bean: add the corresponding validators directly to that decoder.

### 9.3. Adding an Audience Validator While Keeping the Issuer Validator

Example extended version when the API requires `aud` to contain `orders-api`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtContractConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwks = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");
        String audience = env.getRequiredProperty(
            "app.security.expected-audience");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience does not match this API",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        return decoder;
    }
}
~~~

Corresponding YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

This is an **alternative configuration** to the `JwtDecoder` bean in section 9.2; do not declare both beans of the same type/name without a clear purpose.

Checks illustrated by the example:

1. Valid JWS signature against the configured public key source.
2. `iss` claim must match the configured issuer.
3. `exp`/`nbf` satisfy the timestamp validator.
4. `aud` contains the audience required by the application.

Per-endpoint authorization (`scope`/authority/owner) remains part of `SecurityFilterChain` and business logic. For tokens following RFC 9068 or issuer profiles requiring `typ`, `client_id`, `iat`, `jti`, add the corresponding validators.

### 9.4. Mistake When Replacing the Validator Manually

An easy-to-make mistake:

~~~java
decoder.setJwtValidator(jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null)));
~~~

If the snippet above **replaces the entire validator**, it can drop the issuer and timestamp checks previously configured on the decoder. As a result, the application looks only at audience and skips foundational security checks.

Combine it with `JwtValidators.createDefaultWithIssuer(issuer)` (or appropriate equivalent validators), adding checks rather than accidentally removing essential constraints.

## 10. Reading `iss` in a Controller Is Different from Validation

After authentication succeeds, a controller can read the issuer:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    @GetMapping("/api/session-info")
    public Map<String, String> info(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

This is an example of **reading the principal already authenticated by the Resource Server**. In a system using an issuer URI, `jwt.getIssuer()` returns the issuer claim after decoding. When this claim is required and has passed validation, it can be used to establish business context.

**Do not use** the following approach to “authenticate” a token:

~~~java
// INCORRECT: reading an unverified payload and comparing strings in the controller.
String issuer = decodeBase64UrlPayload(rawBearerToken).get("iss");
if (issuer.equals("https://id.example.test/realms/shop")) {
    // self-grant access
}
~~~

An attacker can craft a JSON payload with any `iss` they want. Only once the token's signature is verified against a trusted key and all validators pass does the issuer claim carry security meaning.

The controller example above assumes a valid token always has `sub` and `iss`. In production applications, avoid logging or returning unnecessary claims; only expose metadata in controlled debug/training endpoints.

## 11. Configuring Issuer with Reverse Proxies, Realms, or Multiple Environments

### 11.1. Do Not Use an Internal Host in Place of the Public Issuer

Suppose the Identity Provider runs internally at:

~~~text
http://idp:8080/realms/shop
~~~

But the official public issuer is:

~~~text
https://login.example.test/realms/shop
~~~

JWTs and standard metadata publish:

~~~json
{
  "iss": "https://login.example.test/realms/shop"
}
~~~

The Resource Server must configure the issuer matching **the actual publisher identifier inside the token**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
~~~

If metadata discovery on the public issuer is unreachable from the internal network, you can specify `jwk-set-uri` using a secure routing contract while **still keeping `issuer-uri` set to the public `iss`**. Do not change `issuer-uri` to `http://idp:8080/...` merely for connection convenience.

Prefer fixing the IdP's external issuer/base URL or proxy headers configuration so metadata, JWT `iss`, and public host share one consistent value.

### 11.2. Distinguishing Realms/Tenants

Some IdPs issue a separate issuer per tenant/realm:

~~~text
https://id.example.test/realms/company-a
https://id.example.test/realms/company-b
~~~

A Resource Server trusting only `company-a` will reject tokens whose `iss` is `company-b` unless intentionally configured for **multi-issuer**. Do not check with a rule like `startsWith("https://id.example.test/realms/")` to trust every realm on a domain.

Even when two tenants share a domain, issuer paths usually represent distinct trust boundaries. An allowlist and per-issuer validation are required.

### 11.3. Dev, Staging, and Production Environments

For example:

~~~text
Dev issuer:     https://id-dev.example.test/realms/shop
Staging issuer: https://id-stg.example.test/realms/shop
Prod issuer:    https://id.example.test/realms/shop
~~~

Dev tokens should not be accepted by the production API merely because they share scope names or subjects. Each environment needs its appropriate issuer, key source, and audience. Do not use a relaxed configuration allowing any issuer just to “switch environments easily”.

### 11.4. Truly Multi-Issuer Systems

If the Orders API must accept tokens from multiple Authorization Servers, you cannot just add a single `issuer-uri` value and expect it to accept multiple `iss` values automatically.

Spring Security Servlet provides **`JwtIssuerAuthenticationManagerResolver`** with a list of trusted issuers, for example:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id.example.test/realms/company-a",
        "https://id.example.test/realms/company-b");

http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver)
);
~~~

The snippet above illustrates a **multi-issuer strategy** in Spring Security versions supporting this API; it is an alternative configuration to the direct single-issuer `jwt()` flow, not something to tack arbitrarily onto an incompatible chain.

**Security:** the resolver may need to peek at `iss` in the token before knowing which issuer/manager to pick. At that moment, `iss` is merely an *unverified routing hint*. Allow only issuers in a **trusted allowlist**, and then verify the JWT using the keys/validators belonging to that selected issuer. Never fetch metadata or JWKS from an arbitrary `iss` sent by a client.

## 12. Practice: Predicting Outcomes with `issuer-uri`

Suppose:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Endpoint requiring authentication:

~~~java
http.authorizeHttpRequests(auth ->
    auth.anyRequest().authenticated());
~~~

Cases:

| Case | JWT `iss` | JWT `aud` | Expected |
|---|---|---|---|
| Valid issuer, audience, and validators | `https://id.example.test/realms/shop` | `orders-api` | Passes authentication |
| Wrong realm | `https://id.example.test/realms/other` | `orders-api` | **401** |
| Missing issuer | No `iss` | `orders-api` | **401** |
| Issuer with different trailing slash | `https://id.example.test/realms/shop/` | `orders-api` | **401** |
| Right issuer, wrong audience | `https://id.example.test/realms/shop` | `billing-api` | **401** when audience validator is active |
| Right issuer but expired token | Valid | `orders-api` | **401** |
| Right issuer but bad signature | Valid | `orders-api` | **401** |
| Right issuer, right audience, missing endpoint scope | Valid | `orders-api` | Authentication succeeds; may return **403** when authorization requires scope |
| No token sent to protected endpoint | N/A | N/A | Typically **401** |

None of the JSON payloads in the table suffice to be accepted without a valid signature. Also, “passes authentication” does not guarantee the endpoint returns 200: scope, role, tenant, and business ownership policies still apply.

### 12.1. Sending a Request with curl

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Use a test token issued by the test environment's issuer. If you want to test an incorrect `iss` that still has a valid signature, you must use a **separate test issuer with test keys and controlled trust configuration** or a purposefully built test decoder. Manually editing the JSON payload of an existing JWT invalidates the signature, making it impossible to distinguish issuer errors from signature errors.

### 12.2. Common Responses

Tokens with the wrong issuer are usually rejected by the Resource Server during the JWT validation step. The response can be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Depending on the handler, the message may include more or fewer attributes. Do not expose raw token strings, unnecessary public/private keys, or full claims in public error responses.

If the token is valid but lacks endpoint permissions:

~~~http
HTTP/1.1 403 Forbidden
~~~

Because issuer validation is part of **authentication**, an issuer error falls under invalid JWT (typically 401), unlike when an authenticated principal lacks sufficient scope/role (typically 403).

## 13. Diagnosing Configuration Issues When Real Tokens Are Rejected

### 13.1. “The Token Has a Valid Signature, Yet Still Returns 401”

Check in order:

1. Did Spring Security select the right `SecurityFilterChain` with Resource Server enabled?
2. Does the header follow the `Authorization: Bearer <token>` contract?
3. Does `issuer-uri` **exactly match** `iss` in the issued access token?
4. Does metadata discovery return the right issuer and `jwks_uri`?
5. Did the decoder obtain the right signing public key and permitted algorithm?
6. Are `exp`/`nbf` and clock skew valid?
7. Is `aud` intended for this API?
8. Is the token truly an **OAuth 2.0 access token** rather than an OIDC ID Token?

Simply inspecting the signature or decoding the payload with a Base64URL tool is not enough to conclude a token is valid.

### 13.2. “Same Issuer URI Except for a Trailing Slash”

For example:

~~~text
Configured: https://id.example.test/realms/shop
JWT iss:    https://id.example.test/realms/shop/
~~~

These are two different values under issuer comparison. Fix the configuration or the Authorization Server side so they match. Do not build a validator accepting both just to ignore configuration drift, unless there truly are **two permitted issuers** and an explicit multi-issuer design.

### 13.3. “JWKS Is Reachable, Yet the JWT Still Fails Issuer Validation”

A responsive JWKS lets the decoder find public keys; **it does not prove the `iss` claim matches**. A validly signed token will still be rejected if the issuer claim is wrong. Check `issuer-uri` and provider metadata, then check scope and audience separately.

### 13.4. “Only `jwk-set-uri` Was Declared and Tokens from Another Issuer Get Through”

Without an issuer validator, the decoder may check only signatures and timestamps. Add `issuer-uri` alongside JWKS, or `JwtValidators.createDefaultWithIssuer(...)` when constructing a custom decoder.

Do not fix this by taking the issuer from the token and building a validator **against the token's own claimed value**; that allows any self-declared `iss` to pass issuer validation.

### 13.5. “The Application Does Not Call Metadata at Startup”

This can be completely normal with **lazy discovery** in current Spring Security versions. Starting up successfully does not by itself prove discovery/JWKS endpoints are ready for the first request. Observe both **first authentication request timing** and key/cache health.

Conversely, when the application manually invokes `JwtDecoders.fromIssuerLocation` during bean creation, metadata may be queried early. Do not apply a single startup expectation across all versions/configurations.

### 13.6. “After Key Rotation, New Tokens Cannot Be Verified”

The new public key may not yet be available in JWKS/cache. Inspect `kid` in the JWS header, keys published by the issuer, allowed JWS algorithm configuration, and JWKS refresh behavior. Never disable issuer/signature validation to let new tokens through.

### 13.7. “A Staging Token Accidentally Calls the Production API”

If the production Resource Server trusts the staging issuer (or skips issuer checking) and audience is not tightly constrained, environments can bleed into one another. Define issuer and audience per environment and validate both; do not rely solely on client name or scope checks.

## 14. Operations and Trust Boundaries

### 14.1. The Issuer URI Is Security Configuration

Never take `issuer-uri` from a request header, query parameter, or an unverified `iss` claim. For single-issuer APIs, the issuer value should reside in controlled configuration.

For multi-issuer setups, use an **allowlist** and well-designed tenant rules; never construct metadata URLs dynamically from client-supplied tokens.

### 14.2. Trust Metadata and JWKS Only from Permitted Sources

Discovery uses endpoints of the configured issuer or contracted provider. Connections should use HTTPS with proper certificate validation; avoid arbitrary redirects/URLs to untrusted hosts that introduce SSRF or key-substitution risks.

The `kid` field in a JWT helps pick a key from an already-trusted source; it does not grant permission to download public keys from an arbitrary URL advertised by the token.

### 14.3. Do Not Accidentally Lose the Issuer Validator

If replacing the auto-configured decoder with a custom bean, preserve issuer and timestamp validators before adding others. When calling `setJwtValidator(...)`, remember it **replaces the validator already set** on the decoder rather than automatically appending to prior logic.

### 14.4. Do Not Use Issuer as a Substitute for Data Permissions

The issuer identifies the publisher; it does not mean a user can view all data associated with that issuer. The API still needs to check `aud`, scopes/authorities, tenant, owner, and domain policies.

### 14.5. Difference Between Access Token and ID Token

An OIDC ID Token may carry the right `iss` from the same IdP. However, an ID Token's `aud` is usually the **OIDC client ID**, not the Resource Server. Checking only `iss` is insufficient to prevent mistakenly accepting an ID Token.

Use access tokens intended for the API; enforce audience and token profile per the issuing contract.

## 15. Checklist When Onboarding a New Issuer

| Question | Where to confirm? |
|---|---|
| What is the exact issuer value? | Authorization Server/IdP metadata and the `iss` claim on issued access tokens |
| Does the issuer have a trailing slash? | Exact string match across token, metadata, and config |
| Which discovery endpoint is supported? | OIDC Provider Configuration or RFC 8414 metadata |
| What is the real `jwks_uri`? | Issuer metadata or IdP documentation |
| Must the API start without reaching metadata? | Consider `issuer-uri` + `jwk-set-uri` and Spring Security version |
| Which signing algorithm does the JWT use? | Token contract, JWS header, and allowed algorithms config |
| What is the API's valid audience? | Resource Server contract, usually enforced via `audiences` or validator |
| Does the API accept one or multiple issuers? | Single-issuer architecture or multi-issuer allowlist |
| What happens if `iss` mismatches? | Authentication fails; typically HTTP 401 |
| What is the key rotation policy? | IdP/JWKS, caching, and Resource Server operations |
| Which endpoints require which scopes? | `SecurityFilterChain`, method security, business policy |

Integration documentation should record the **verbatim issuer value**. A line like “issuer: the company's IdP server” is not enough to configure `issuer-uri` accurately.

## 16. Key Takeaways

- **`issuer-uri`** configures the **Authorization Server/issuer that the Resource Server trusts**.
- Spring Security uses that issuer for **metadata/JWKS discovery** when appropriate, while also validating the **JWT `iss` claim** against the configured issuer.
- **`iss` must match the expected value**; a different realm, scheme, or trailing `/` can cause the JWT to be rejected.
- **JWKS URI** supplies public keys; it is **not the issuer**. Configuring only `jwk-set-uri` without an issuer validator can skip validating `iss`.
- Declaring **both `issuer-uri` and `jwk-set-uri`** keeps issuer validation while explicitly pointing to the public key location.
- When supplying a custom `JwtDecoder`, **attach/preserve issuer and timestamp validators**, and add audience and claim validators according to the API contract.
- **Issuer validation does not replace audience, signature, expiration, token type, or business permission checks**.
- For multi-issuer systems, use an **allowlist and a dedicated resolver**; never trust an arbitrary issuer supplied by an unverified token.
- `iss` errors are typically **authentication failures → 401**, whereas valid tokens lacking permissions are typically **authorization failures → 403**.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Boot Reference — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security API — JwtDecoders](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoders.html)
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security API — JwtIssuerValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtIssuerValidator.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
