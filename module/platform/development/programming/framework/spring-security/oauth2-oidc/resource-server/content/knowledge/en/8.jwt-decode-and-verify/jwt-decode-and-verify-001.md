# JwtDecoder and the Difference Between Parsing and Verification

In **Spring Security OAuth 2.0/OIDC Resource Server**, an API typically receives an access token via an HTTP header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

An access token can be a JWT containing claims such as **iss**, **sub**, **aud**, **exp**, and **scope**. A JWS-signed JWT typically allows anyone holding the token to Base64URL-decode the payload and read the JSON immediately. Therefore, a dangerous misconception is assuming that **being able to read the payload means the token has been authenticated**.

**Parsing only shows what the token claims; signature verification tells whether that content is protected by a trusted key; validation determines whether the token is valid for the API at the current time.** Only after these three steps does the application perform authorization for the specific endpoint and data.

Spring Security provides **JwtDecoder** as the JWT processing boundary. In a typical JWT Resource Server configuration, **NimbusJwtDecoder** parses the JWT, verifies the signature, and applies the configured validators. The name “decoder” thus carries a broader meaning than a mere Base64URL decode operation.

## 1. Four distinct operations: parse, verify, validate, authorize

| Operation | Purpose | Example | Limitation |
|---|---|---|---|
| **Parse / syntax decode** | Split header, payload, signature; read JSON data | Seeing **sub = user-123**, **scope = orders.read** | Does not verify whether the data is authentic or tampered with |
| **Verify signature/MAC** | Check cryptographic protection using a trusted key and algorithm | Verify RS256 signature with the issuer's RSA public key | A valid signature does not prove the token is meant for this API |
| **Validate claims** | Check **iss**, **aud**, **exp**, **nbf**, token type, and acceptance policy | Reject a token with audience **payments-api** at the Orders API | A valid token does not prove the user can read every order |
| **Authorize action/resource** | Check business permissions, role/scope, tenant, owner, resource state | **orders.read** and order 42 belongs to the user's scope | Must occur at the appropriate endpoint/service/domain policy layer |

A few examples clearly illustrate the difference:

1. The payload contains **ROLE_ADMIN**, but the sender edited the JSON themselves: parsing still succeeds; signature verification **fails**.
2. The token is validly signed by the issuer, but **aud** is a different API: signature verification **passes**, claim validation **fails**.
3. The token has valid **iss/aud/exp** and was granted **orders.read**, but is reading an order from another tenant: the token is authenticated, resource-level authorization **fails**.

Thus, a JWT with valid JSON is not proof of login, and a properly signed JWT is not a license to access arbitrary data.

## 2. JWT/JWS structure explains why confusion happens easily

A JWT signed with **JWS Compact Serialization** usually has three parts separated by dots:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
          part 1                    part 2                 part 3
~~~

Example of a decoded protected header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "shop-sign-2026-11"
}
~~~

Example of a decoded payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000,
  "tenant_id": "tenant-a"
}
~~~

These are **illustrative** JSON snippets, not a signed JWT capable of calling an API. Meaning:

- **alg** is the signature algorithm the token declares it uses, such as RS256.
- **kid** is an identifier hinting which public key to select from a trusted JWKS.
- **typ** indicates the token/profile type; **at+jwt** is commonly used for JWT access tokens per RFC 9068.
- **iss** is the issuer that the token claims issued it.
- **sub** is the subject identifier within the issuer's context.
- **aud** is the intended recipient, in this example **orders-api**.
- **exp** is the expiration time in NumericDate format.
- **scope** describes the scopes granted under the issuer's OAuth2 policy.
- **tenant_id** is a custom claim, usable only under a trust contract and corresponding business permission checks.

The JWS signature is computed over the **signing input itself**, consisting of the first two Base64URL segments joined by a dot:

~~~text
ASCII(BASE64URL(protected-header) + "." + BASE64URL(payload))
~~~

If the payload is modified from **orders.read** to **orders.write** without regenerating the signature using the appropriate key, the verification step must fail.

**Base64URL is not encryption.** Anyone holding a regular JWS JWT can read the header and payload even without a private key. A JWT signature protects integrity/authenticity, not claim confidentiality. Avoid placing passwords, secrets, or unnecessary private data inside the payload.

### 2.1. Not every Bearer token is a three-part JWT

- **JWS Compact Serialization** typically has three parts.
- **JWE Compact Serialization** typically has five parts and encrypts data; decryption requires the appropriate algorithm/key.
- **Nested JWT** may combine JWS and JWE.
- **Opaque token** may simply be a random string; a Resource Server typically verifies it via introspection.

**JwtDecoder** is used for JWTs in formats supported by the implementation. For opaque tokens, Spring Security uses **OpaqueTokenIntrospector**—never manually split a token by dots and infer its content.

## 3. Mere Base64URL decoding of a JWT is not authentication

A plain Java snippet to inspect the payload:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class UntrustedJwtViewer {

    // For structure illustration only. DO NOT use for authentication or authorization.
    public static String readUntrustedPayload(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected a three-part JWS");
        }
        byte[] bytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

This snippet can read a payload such as:

~~~json
{
  "sub": "attacker",
  "scope": "orders.read orders.write",
  "role": "ADMIN",
  "exp": 4102444800
}
~~~

However, the sender **can fabricate the entire payload**. Decoding into UTF-8 and parsing into JSON only indicates that the string is syntactically valid data. Dots, Base64URL, and JSON provide no protection against forgery.

**Do not** write logic like the following:

~~~java
// WRONG: claims have not been verified.
String payload = UntrustedJwtViewer.readUntrustedPayload(rawBearerToken);
Map<String, Object> claims = readJson(payload);
String role = (String) claims.get("role");
grantRole(role);
~~~

This snippet illustrates a **design flaw**, where **readJson** and **grantRole** are hypothetical names. No matter how good the real JSON library is, permissions are being derived from self-asserted sender data. An attacker can modify the role or scope and resend a forged token.

The right approach is to let the Resource Server verify the token via **JwtDecoder** first, and only then build **Authentication/GrantedAuthority** from the accepted claims.

## 4. Spring Security's JwtDecoder interface

The core interface resides in the package **org.springframework.security.oauth2.jwt**:

~~~java
public interface JwtDecoder {
    Jwt decode(String token) throws JwtException;
}
~~~

This is a simplified form to explain the API contract. At runtime:

- **Input** is a compact JWT string.
- **Output** is a **Jwt** object containing the token value, headers, claims, and Spring Security accessors.
- **Failure** is signaled by throwing **JwtException** or an appropriate subtype.

**NimbusJwtDecoder** is the standard implementation in a Servlet JWT Resource Server. It uses Nimbus JOSE + JWT to process the JOSE structure, verify the signature with a trusted key, and execute the configured **OAuth2TokenValidator<Jwt>** instances.

| Component | Responsibility |
|---|---|
| **JwtDecoder** | Contract for decoding and validating a JWT |
| **NimbusJwtDecoder** | Nimbus JOSE/JWT-based implementation, configured with key source and algorithms |
| **Jwt** | Representation of a token accepted by the decoder, including claims/headers |
| **JwtValidators** | Creates standard validator sets, including issuer and timestamp checks |
| **OAuth2TokenValidator<Jwt>** | Checks a condition on a Jwt; multiple validators can be composed |
| **JwtAuthenticationProvider** | Uses JwtDecoder to authenticate a Bearer JWT |
| **JwtAuthenticationConverter** | Converts an accepted Jwt into an Authentication and authorities |
| **SecurityFilterChain** | Configures authentication, request handling, and HTTP authorization |

**Warning about the word “decoder”:** In Spring Security, a standard JwtDecoder does not merely convert Base64URL to JSON. Conversely, if a developer writes a custom **JwtDecoder** implementation that only parses JSON and returns a **Jwt**, they break the token-verification responsibility of the interface itself. The framework does not re-verify the signature for an insecure custom decoder.

### 4.1. Successful decoding does not mean access to all resources

Suppose the decoder returns a Jwt with the claim **scope = orders.read**. The default converter typically maps the scope to the authority **SCOPE_orders.read**. An endpoint might require:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

This condition only checks permission at the operation-type level. The service must still check the owner, tenant, assigned permissions, and status of **order 42**. A JWT signature and JwtDecoder cannot replace business policy.

## 5. Where does JwtDecoder sit in the Bearer token authentication flow?

For a Servlet Resource Server, the logical flow is typically:

~~~mermaid
flowchart TD
    A[Request with Authorization: Bearer] --> B[BearerTokenAuthenticationFilter]
    B --> C[AuthenticationManager and JwtAuthenticationProvider]
    C --> D[JwtDecoder.decode]
    D --> E[Parse untrusted header/payload]
    E --> F[Select key and algorithm from trusted config]
    F --> G{Valid JWS signature?}
    G -->|No| X[Authentication failed: 401]
    G -->|Yes| H{Validators pass?}
    H -->|No| X
    H -->|Yes| I[JwtAuthenticationConverter]
    I --> J[JwtAuthenticationToken / GrantedAuthority]
    J --> K{Sufficient endpoint and data permissions?}
    K -->|No| L[403 or 404 per policy]
    K -->|Yes| M[Controller / Service handles request]
~~~

Step by step:

1. **BearerTokenAuthenticationFilter** extracts the token from the HTTP request using the Bearer mechanism.
2. **JwtAuthenticationProvider** is used in a JWT Resource Server configuration.
3. The provider calls **JwtDecoder.decode()**.
4. The decoder checks the structure, algorithm, signature, and configured validators.
5. After the decoder returns a valid Jwt, **JwtAuthenticationConverter** maps claims to the principal and authorities.
6. Web/method/service authorization decides whether access is permitted.

If the decoder throws a **JwtException**, the request is treated as an authentication failure; for a Bearer API this is typically **401 Unauthorized**. If authentication succeeds but permissions are lacking, it is typically **403 Forbidden**.

The flowchart is a logical illustration, not the exact internal method call order for every Spring Security version. The security boundary to maintain is **never accepting claims to grant permissions before the JWT verification step**.

## 6. What does “verifying a JWT” need to check?

### 6.1. Signature and allowed algorithms

For an **RS256** token:

- The Authorization Server uses an **RSA private key** to sign.
- The Resource Server uses an **RSA public key** from a trusted source to verify.
- The API does not need the issuer's private key.

For **ES256**, the approach is similar but uses EC keys and ECDSA. For **HS256**, both the signer and verifier share a secret HMAC key, so key protection scope differs from the public-key model.

Spring Security documentation describes **NimbusJwtDecoder** as trusting only **RS256** by default in a standard JWT Resource Server configuration, while providing ways to configure additional algorithms when the issuer actually uses them.

Do not automatically switch from RSA verification to HMAC just because the token header says **alg = HS256**. Do not accept **alg = none** if the system requires signed JWTs. Do not let the token itself dictate the set of algorithms accepted by the Resource Server. Such mistakes can lead to **algorithm confusion**.

### 6.2. Public keys and JWKS

A JWT may carry a **kid** in its JOSE header, for example:

~~~json
{
  "alg": "RS256",
  "kid": "shop-sign-2026-11"
}
~~~

The Resource Server uses **kid** as a hint to look up a key in the **JWKS of the configured trusted issuer**. It must never fetch JWKS from an arbitrary URL declared by an unverified JWT in **jku** or **x5u**.

If an application trusts a **jku** sent by an attacker, the attacker can sign a JWT with their own private key, publish their own public key, and instruct the API to use that exact public key to “verify” it. Allowing untrusted URL fetches can also cause SSRF.

To protect the trust chain:

- Pin the issuer/JWKS URI via server configuration or an allowlist of permitted issuers.
- Connect to metadata/JWKS over HTTPS with certificate verification.
- Accept only appropriate keys, key types, and algorithms.
- Support rotation with old/new public keys during a transition window.
- Never allow bypassing signature verification when JWKS fails or no matching **kid** exists.

### 6.3. Issuer: was the token issued by the right authority?

The **iss** claim must match the issuer trusted by the API.

~~~text
Configured issuer: https://login.example.com/realms/shop

Accepted JWT iss: https://login.example.com/realms/shop
Rejected JWT iss: https://login.example.com/realms/another
~~~

**A valid signature against just any key** is not enough. You must ensure the key belongs to the issuer delegated by the API. In a multi-issuer/multi-tenant system, each trust source may have a distinct JWKS; **kid** values can collide across issuers, so never look up solely by kid globally while ignoring the issuer.

### 6.4. Audience: is the token meant for this Resource Server?

An issuer can issue JWTs for multiple APIs. The Orders API must reject a properly signed token with:

~~~json
{
  "aud": ["payments-api"]
}
~~~

If the API requires **orders-api**, the audience check must confirm that the **aud** list includes that value.

A common mistake is configuring only **issuer-uri**, which enables issuer/timestamp validation by default, while forgetting to configure the API's **audiences**. A validly signed JWT issued by the trusted issuer can then still be misused against the wrong target recipient.

### 6.5. Timestamps: exp, nbf, and iat

| Claim | Meaning | Example rule |
|---|---|---|
| **exp** | Expiration timestamp of the token | Do not accept the token after exp, considering an appropriate clock skew tolerance |
| **nbf** | Token is not valid before this time | Do not accept the token too early |
| **iat** | Timestamp when the token was issued | Can be used in token-age policies, but does not replace exp/nbf |

Spring Security uses time validators such as **JwtTimestampValidator**, and provides mechanisms to configure clock skew tolerance. Do not increase clock skew excessively just to “fix” expiration errors; synchronize clocks between the Authorization Server and Resource Server.

A properly signed but expired JWT must still be rejected. If the application needs immediate permission revocation while a token has not yet expired, consider appropriate token lifetime policies, introspection, revocation, or dynamic permission checks.

### 6.6. Token type and profile

An OIDC **ID Token** can also be a JWT signed with the OpenID Provider's key. However, it is meant for the **OIDC client** to verify a login event; a Resource Server needs an **access token** intended for that purpose.

You must check **audience** and the token type/profile requirements agreed upon by the API and the issuer. In ecosystems using RFC 9068, JWT access tokens have specific requirements and may use **typ = at+jwt**. If enforcing this profile is required, configure an appropriate validator; merely reading typ from an unverified header/payload is insufficient.

**sub**, **tenant_id**, roles, and permissions must also have well-defined semantics. An email address, profile, or email domain does not automatically become a business permission.

## 7. Configuring JwtDecoder via Spring Boot

A Spring MVC API usually starts with the Spring Boot starter for **OAuth2 Resource Server**, letting Boot manage the Spring Security and JOSE modules.

| Spring Boot generation | Resource Server starter |
|---|---|
| **Spring Boot 3.x** | **spring-boot-starter-oauth2-resource-server** |
| **Spring Boot 4.x** | **spring-boot-starter-security-oauth2-resource-server** |

For JWT, Spring Security OAuth2 Resource Server and **spring-security-oauth2-jose** are needed underneath. When using the Boot-managed starter, these dependencies are aligned with the release line; avoid pinning individual Security modules from a different generation.

### 7.1. Issuer URI and audience

In **application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

When no custom JwtDecoder bean replaces it, Spring Boot/Spring Security can auto-configure a decoder that uses the trusted issuer's metadata/JWKS and verifies the signature, issuer, and expiration. The **audiences** property in supported Boot versions sets the audience for the API.

Example values must be replaced with actual token-issuing settings. **issuer-uri does not automatically generate scopes or business permissions**, and you must confirm that the configuration properties match the Spring Boot release in use.

### 7.2. Specifying the JWK Set URI

You can specify the JWKS URI explicitly:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri** specifies where to fetch public keys, while **issuer-uri** is still needed to verify **iss**. If only a JWKS URI is set without an issuer validator, a custom configuration may lack sufficient policy to properly distinguish the issuer.

Do not pass the JWKS URI in a query parameter and let the client choose it. The key source belongs to the Resource Server's trust configuration.

### 7.3. SecurityFilterChain authorizing requests after decoding

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

This example is for **Spring Security Servlet**, not WebFlux. If the token is valid but lacks the **orders.read** scope, the endpoint is blocked. If the scope is present but the order belongs to another tenant, the service/domain policy must still deny it.

Do not build authorities from a JSON request body or a token that has not gone through JwtDecoder. In the default flow, **JwtAuthenticationConverter** operates on a Jwt already accepted by the provider.

## 8. Building a custom NimbusJwtDecoder and attaching validators

There are cases where you must customize the decoder to specify an algorithm, use a particular JWKS URL, or add audience/token profile checks. The following example uses Spring Security APIs and accepts only **RS256**, the trusted issuer, valid timestamps, and the **orders-api** audience.

~~~java
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
class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWK_SET_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWK_SET_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token was not issued for orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );

        return decoder;
    }
}
~~~

Meaning:

1. **withJwkSetUri(...)** fetches public keys from the endpoint configured by the Resource Server.
2. **jwsAlgorithm(RS256)** restricts the accepted signature algorithm.
3. **JwtValidators.createDefaultWithIssuer** applies standard validation, including timestamps and issuer.
4. The **audience** validator checks that the token was issued for the Orders API.
5. **DelegatingOAuth2TokenValidator** combines the conditions that must all pass simultaneously.
6. The decoder returns a Jwt when the token meets all requirements, or reports an error if it fails.

**Warning about custom beans:** When defining a **@Bean JwtDecoder**, that bean can replace the Boot auto-configured decoder. Do not assume that JWT configuration properties in **application.yml** still automatically attach every validator to a custom decoder. You must explicitly configure the issuer, audience, token type, and any other required checks.

### 8.1. Do not replace the validator and forget the default checks

Example of the issue:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwkSetUri)
    .build();

// FLAWED DESIGN IF ALL issuer/timestamp validators ARE OMITTED:
// decoder.setJwtValidator(onlyMyCustomValidator);
~~~

**setJwtValidator** sets the validator on the decoder. If a developer attaches only a custom rule and omits the standard validators, they may inadvertently skip checking **iss** and **exp/nbf** as expected. When adding a rule, compose it with the required default/issuer validators.

### 8.2. A custom decoder can also affect metadata loading timing

Spring Security and Spring Boot have issuer/JWKS discovery, key caching, and may defer some network operations until the first request depending on configuration. When replacing the decoder, startup behavior, timeouts, and caching may differ. In production, verify HTTPS connection settings, JWKS key rotation, metadata caching, and how the system behaves when the Authorization Server is temporarily unreachable. Never work around JWKS connectivity loss by accepting unverified tokens.

## 9. Distinguishing “decode” methods across JWT libraries

A method name alone is not enough to understand the security guarantees of its output:

| Operation | Verifies signature? | Validates claims per API policy? |
|---|---|---|
| Splitting string by dots | No | No |
| Base64URL decoding header/payload | No | No |
| JSON parser converting payload to Map/DTO | No | No |
| JWT parser only constructing syntax objects | No, if the library has not run a verifier | No |
| JWS verifier with a trusted key | Can verify signature | Usually requires separate claim validators |
| Properly configured **NimbusJwtDecoder.decode** | Yes, for supported JWT/JWS | Yes, according to the configured validator set |
| **JwtAuthenticationConverter** | Does not verify signature itself | Maps authorities, does not replace JwtDecoder |

Some external libraries use names like **parseSignedClaims**, **verify**, **decode**, or **claims** differently. When reviewing code, ask:

- Where is the actual **JWS signature/MAC** verification call?
- Where do the key/algorithm come from and under what policy are they trusted?
- Where are the **iss/aud/exp/nbf** validators executed?
- What steps has the returned claims object gone through?
- On failure, does the method throw an exception, return an invalid status, or still return JSON?

Never manually construct a **Jwt** or **JwtAuthenticationToken** from unverified data and treat it as safe. Every authentication boundary must uphold the token-verification contract.

## 10. Example of a payload-tampering attack

Suppose an originally valid token has:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

An attacker takes the payload, replaces it with:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"]
}
~~~

then re-encodes it with Base64URL and sends the token with the old signature.

Expected outcome:

| Step | Result |
|---|---|
| Split token into three parts | May succeed |
| Read JSON | May succeed; sees added **orders.write** |
| Verify old signature against new signing input | **Fails** |
| NimbusJwtDecoder | Reports invalid token |
| Spring Security authentication | Does not create an authenticated principal for the tampered token |
| Call endpoint requiring write permission | **Denied**, typically 401 because the token is forged |

If the API merely parses the **scope** claim without verifying, the request could be granted write permission even though the attacker has no private key whatsoever. Thus, **being able to parse JSON is an extremely weak condition** and carries no authentication meaning.

Do not implement signature verification algorithms manually for production applications. Use a trusted JOSE framework/library and properly configure the key source, issuer, and audience.

## 11. Understanding 401 vs. 403 responses properly

| Scenario | Verification / authorization | Typical HTTP status |
|---|---|---|
| No Bearer token sent | Unauthenticated | **401** |
| Malformed JWT structure | Parsing fails | **401** |
| Valid payload but invalid signature | Cryptographic verification fails | **401** |
| Valid signature, untrusted issuer | Issuer validation fails | **401** |
| Valid signature, audience is another API | Audience validation fails | **401** |
| Token expired or before nbf | Time validation fails | **401** |
| Authenticated JWT lacking **orders.read** | Authorization fails | **403** |
| JWT has scope but cannot view the specific order | Resource policy fails | **403**, or **404** per hiding policy |
| Valid JWT, sufficient scope and record-level permission | Conditions met | Endpoint proceeds, may return **200** |

For a Bearer API, a 401 response typically carries the **WWW-Authenticate: Bearer** header. The actual status code may vary depending on exception handling configuration. You must distinguish invalid tokens (to fix authentication configuration) from insufficient permissions (to fix policy/role mapping properly).

Never fix a 401 by removing signature/audience validators, and never fix a 403 by setting **permitAll()** on sensitive endpoints.

## 12. Testing a real JwtDecoder and mocking JWT are two different goals

Spring Security Test provides the **jwt()** request post-processor to inject a simulated principal/JWT into the SecurityContext in Servlet tests. This is appropriate for testing authorization, but **does not necessarily execute the real JwtDecoder**.

Illustrative example:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void allowsReadScopeInWebRule() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(() -> "SCOPE_orders.read")))
        .andExpect(status().isOk());
}
~~~

This condensed test assumes **mockMvc**, the controller, order fixtures, and appropriate policies exist to return 200. Without data, a real test might return 404 even when the user is authorized. The key point: **mocking jwt() tests Security rules; it does not prove that forged tokens will be rejected by JwtDecoder**.

Test layers should be kept distinct:

1. **Web/method authorization test**: mock JwtAuthenticationToken to test scope/role/tenant requirements and 403 outcomes.
2. **Decoder test**: use a **real JWT signed with a test key**, or tokens that are tampered, have the wrong audience/issuer, or are expired, to test **JwtDecoder.decode**.
3. **HTTP integration test**: send a test Bearer token through the filter chain with a trusted mock issuer/JWKS to verify 401/403 and authority mapping.
4. **Operations**: verify JWKS over HTTPS, certificates, key rotation, caching, and timeouts in a real environment.

Illustrative guidance for a decoder test:

~~~java
// validSignedToken: JWT signed with the test issuer's private key.
// tamperedToken: token with a modified payload that was not re-signed.

Jwt jwt = jwtDecoder.decode(validSignedToken);

assertThrows(
    JwtException.class,
    () -> jwtDecoder.decode(tamperedToken)
);
~~~

This is **pseudocode drawn from a test context**; test variables must be created in fixtures and executed against a JwtDecoder configured with test keys/issuer/audience. Never commit real access tokens to source control or logs.

If you rely solely on mocking **jwt()**, the entire test suite can still pass green even if the production custom JwtDecoder skips signature verification. That is why you must verify the actual decoder boundary with appropriate tests during implementation.

## 13. Common pitfalls to avoid

### 13.1. Validly signed JWT used against the wrong API

An issuer can issue tokens for multiple resources. The Orders API must reject a token with **aud = analytics-api**, even with the same issuer and a valid signature. Checking **aud** prevents token substitution.

### 13.2. Trusting JWT data before verification

The JSON payload, **iss**, **kid**, **jku**, scope, and tenant_id can be arbitrarily crafted by an attacker before the signature is checked. Never use them to grant permissions, fetch arbitrary URLs, or query an uncontrolled key store.

### 13.3. Confusing an ID Token with an Access Token

An OIDC ID Token contains login information for the client, whereas a Resource Server needs an access token with the right audience/token profile. Both may be JWTs signed by the same issuer, but they must not be interchanged arbitrarily.

### 13.4. Ignoring expiration because the signature is valid

If **exp** has passed or **nbf** has not been reached, the token must not be used. A signature only proves the content is intact under a trusted key; it does not make a token valid indefinitely.

### 13.5. Writing a custom JwtDecoder that only parses JSON

A custom decoder must perform JWT and claim verification according to the contract. Returning **new Jwt(...)** from a client-sent Map does not meet security requirements, even if the constructed Java class has the same Jwt type returned by Nimbus.

### 13.6. Treating **SCOPE_*** as automatic permission for all data

Spring Security maps scopes into authorities for convenient authorization. It does not inherently understand tenants, record owners, or business policies. These conditions must be enforced at the Resource Server.

### 13.7. Logging raw tokens to debug authentication failures

A Bearer token is a reusable credential. Never put tokens into URLs, access logs, traces, exception reports, bug tickets, or README files. Log a request ID, generic error code, and redacted operational details.

### 13.8. Allowing arbitrary algorithms or JWKS

A JWKS containing a public key is not automatically trustworthy. The key source must belong to the server/issuer trust configuration and the algorithm must be permitted. This principle is emphasized in **RFC 8725 — JWT Best Current Practices**.

## 14. Secure implementation workflow for a Resource Server

Example project constraints:

~~~text
Issuer:          https://login.example.com/realms/shop
Audience:        orders-api
Allowed alg:     RS256
API scope:       orders.read
Business rule:   Only read permitted orders within the user's tenant
~~~

Workflow:

1. The client sends **Authorization: Bearer** over HTTPS.
2. The Resource Server selects the configured **JwtDecoder** to check the JWT access token.
3. The decoder parses the token without trusting claims yet, selecting the algorithm/key from the trusted issuer/JWKS.
4. The decoder verifies the **JWS signature**; tampered or forged tokens are rejected.
5. The decoder runs validators: **iss**, **aud**, **exp**, **nbf**, token type/profile, and other specified constraints.
6. Spring Security maps the valid Jwt to a **JwtAuthenticationToken** and authorities.
7. Web/method authorization checks **SCOPE_orders.read**.
8. Domain policy checks tenant, ownership, membership, and order state before returning data.

When designing or reviewing, the key questions are: where do keys come from, which algorithms are allowed, who attaches the issuer/audience validators, is a custom decoder complete, which tests run the real decoder, where are per-resource permissions enforced, and are tokens ever written to logs.

## Conclusion

**Parsing** a JWT only reads what the token is claiming. **Signature verification** checks whether the header/payload are protected by a trusted key and algorithm. **Validation** verifies that the token has the right issuer, audience, lifetime, and intended purpose. **Authorization** decides whether the subject is allowed to perform the action on a specific resource.

With Spring Security OAuth2 JWT Resource Server, **JwtDecoder** is the core boundary for token authentication: a properly configured **NimbusJwtDecoder** does much more than Base64URL decoding, and only returns a **Jwt** when the token passes the decoder's checks. Do not grant permissions from unverified JSON, do not omit audience/issuer validators when creating a custom decoder, and do not treat a valid signature as permission to access all data.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
