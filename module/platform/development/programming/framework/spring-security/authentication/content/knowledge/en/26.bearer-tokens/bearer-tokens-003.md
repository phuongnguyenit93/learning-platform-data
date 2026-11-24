# JwtAuthenticationProvider, JwtDecoder, and Resulting Authentication

## 1. Problem: From Bearer JWT to Authenticated User in Spring Security

An HTTP API receives a request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

Inside a Spring Security Servlet Resource Server, receiving a token **does not mean** authentication succeeded. The request must go through Bearer token extraction, JWT decoding, signature/claims verification, conversion of valid claims into an `Authentication`, and finally authorization checks on the endpoint or business resource.

Three core types:

- **`JwtDecoder`:** takes a JWT string, verifies it, and produces a `Jwt`; conditions such as signature, timestamps, issuer, and audience must be enforced using an appropriate decoder and validators.
- **`JwtAuthenticationProvider`:** the `AuthenticationProvider` implementation for Bearer JWTs. It invokes the decoder and converter, returning an authenticated `Authentication` or throwing an authentication failure.
- **`JwtAuthenticationToken`:** the default resulting `Authentication` type, holding the `Jwt`, principal name, `GrantedAuthority` collection, and authenticated status.

A fourth key component is **`JwtAuthenticationConverter`**, which decides which claim provides the principal name and which claim provides authorities. The same JWT may contain `sub=user-42`, `preferred_username=alice`, and `scope=orders.read`; each value has a distinct meaning.

This lesson focuses on **Spring Security Servlet (MVC), Java 17+, Spring Boot 3.x / Spring Security 6.x**. WebFlux uses `ReactiveJwtDecoder` and `JwtReactiveAuthenticationManager`, so it does not directly use the same filter/provider classes as Servlet.

After this lesson, you should be able to answer:

1. Which components does the Bearer header pass through, and which step performs true verification?
2. How do the responsibilities of `JwtDecoder` differ from `JwtAuthenticationProvider`?
3. What do `JwtAuthenticationToken.getPrincipal()`, `getName()`, and `getAuthorities()` return?
4. When the signature is valid but the audience is wrong or a scope is missing, what should the response be?
5. How do you customize the converter and test it without mistaking mock unit tests for proof of real-world JWT verification?

## 2. Full Processing Flow

```text
Client -> Authorization: Bearer <jwt>
                 |
                 v
       SecurityFilterChain (Servlet)
                 |
                 v
       BearerTokenAuthenticationFilter
         - BearerTokenResolver extracts token string
         - creates BearerTokenAuthenticationToken (unauthenticated)
                 |
                 v
       AuthenticationManager / ProviderManager
                 |
                 v
       JwtAuthenticationProvider
                 |
                 +------> JwtDecoder.decode(rawToken)
                 |          |
                 |          +-- verify signature/algorithm/trusted key
                 |          +-- validate exp/nbf/iss/aud... per config
                 |          +-- return Jwt or throw JwtException
                 |
                 +------> JwtAuthenticationConverter
                            |
                            +-- name from sub (default)
                            +-- authorities from scope/scp (default)
                            |
                            v
                     JwtAuthenticationToken
                 |
                 v
       SecurityContextHolder / request SecurityContext
                 |
                 v
       AuthorizationFilter, @PreAuthorize, business ACL
                 |
           allow or deny
```

**BearerTokenAuthenticationToken is the input; JwtAuthenticationToken is the result.** `BearerTokenAuthenticationToken` only holds an untrusted credential; never extract claims directly from it to grant permissions.

`JwtDecoder` returns a `Jwt` only after the token passes the configured verification steps. This differs from Base64URL-decoding a JWT: decoding the payload can read an attacker-injected `role=ADMIN`, which **does not prove** the role or signature is valid.

`JwtAuthenticationProvider` takes the decoder result, converts it into an `Authentication` via the converter, and hands it back to the manager/filter. The provider does not own HTTP endpoints and does not decide whether the user can read order 42. The final decision belongs to authorization.

### Distinguishing Data at Each Stage

| Layer | Value Type | Level of Trust |
| --- | --- | --- |
| HTTP request | String in `Authorization` | Untrusted |
| Filter/manager | `BearerTokenAuthenticationToken` | Authentication request, unverified |
| Decoder | `Jwt` | Passed configured signature/validators |
| Provider/converter | `JwtAuthenticationToken` | Authenticated `Authentication`, carrying principal/authorities |
| Authorization | Resource policy outcome | Allowed or denied for this operation |

The flow above is for JWTs. If the access token is an **opaque** string, use introspection (`OpaqueTokenIntrospector`) and its corresponding authentication mechanism; do not feed an opaque token into `JwtDecoder` or try to parse it ad hoc.

## 3. JwtDecoder: Verifying Validity Before Trusting Claims

The core interface exposes `Jwt decode(String token) throws JwtException`. For JWS-signed JWTs under standard configuration, Spring Security uses `NimbusJwtDecoder` to handle signatures, algorithms, public keys/JWKS, and validators. The returned `Jwt` holds the token value, headers, claims, and accessors for timestamps, issuer, subject, and audience.

An illustrative payload:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1796205600,
  "iat": 1796202000,
  "scope": "orders.read orders.write",
  "preferred_username": "alice"
}
```

**This is illustrative JSON only; it is not a signed JWT.** A real decoder must verify the token before the application is permitted to trust the claims.

### What Must Be Verified

**Signature and algorithm.** The decoder must accept only signing algorithms on the designed allowlist and keys from a trusted issuer/JWKS. Never let the token's self-declared `alg` bypass signature checks or choose an arbitrary algorithm. For RS256/ES256 JWTs, the resource server verifies using the corresponding public key and must handle key rotation safely.

**Issuer (`iss`).** The token must be issued by an issuer the API trusts. Even if two tenants share a domain or JWKS, `iss` must not be conflated unless policy permits it.

**Timestamps (`exp` and `nbf`).** Expired or not-yet-valid tokens must be rejected per validators and reasonable clock skew. `iat` is the issuance time; if tokens must not be too old, enforce a dedicated token-age policy.

**Audience (`aud`).** A valid signature and matching issuer are still insufficient: the token may be meant for another API. With some `issuer-uri` setups, issuer/time checks are included, yet the application must **ensure an appropriate audience validator is present**; never assume `aud` is always checked as expected.

**Token type and profile.** An OAuth2 access token for an API differs from an OIDC ID token for a client. When applying a JWT access token profile (such as RFC 9068), verify profile/`typ`, issuer/audience/required claims per system rules. A "validly signed" JWT is not automatically a bearer access token for every resource.

**Revocation.** A valid signature, `exp`, and `aud` do not reflect whether the user logged out or the token was revoked at the authorization server. If near-immediate revocation is required, consider short TTLs, introspection, denylists, or appropriate events/versions. By default, `JwtDecoder` does not query the IdP about user sessions.

### Example of Combining Validators

Do not write:

```java
// DANGEROUS: only the custom validator remains, potentially dropping
// issuer/timestamp checks that existed previously.
decoder.setJwtValidator(
    new JwtClaimValidator<java.util.List<String>>(
        "aud", audiences -> audiences.contains("orders-api")));
```

Instead, combine both the default validator and the application validator:

```java
OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> audience =
    new JwtClaimValidator<java.util.List<String>>(
        JwtClaimNames.AUD,
        aud -> aud != null && aud.contains("orders-api"));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
```

These are **snippets** placed inside a `JwtDecoder` configuration method, requiring appropriate imports and an `issuer` variable. `setJwtValidator(...)` overwrites the existing validator; combine properly to retain issuer/time validation.

## 4. JwtAuthenticationProvider: Bridge to AuthenticationManager

`JwtAuthenticationProvider` implements `AuthenticationProvider` and receives a decoder via its constructor:

```java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(jwtDecoder);
```

The provider supports `BearerTokenAuthenticationToken`, calling the decoder and converter. If the decoder throws `BadJwtException`, the provider translates the error into an authentication failure and produces no success result. Other infrastructure/`JwtException` errors may throw different exception types, so do not assume every error returns the exact same HTTP status without checking exception handling configuration.

If the decoder returns a valid `Jwt`, `JwtAuthenticationProvider` uses the default `JwtAuthenticationConverter` (or a configured one) to produce an `AbstractAuthenticationToken`, typically `JwtAuthenticationToken`. This result already has `isAuthenticated()==true`.

With `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`, Spring Security wires the filter and provider automatically. **There is no need to register the provider manually** just to accept JWTs; manual instantiation is mainly for isolated testing or specialized configurations.

### Responsibilities Not Owned by JwtAuthenticationProvider

- Does not issue JWTs and does not perform OAuth2 authorization code/token exchange.
- Does not renew refresh tokens.
- Does not query data-level permissions for individual orders unless you write corresponding authorization logic.
- Does not create web login sessions from ID tokens; that is a separate OIDC login mechanism.
- Does not define issuer, audience, algorithm, or trusted-key policy itself; policy comes from the decoder and configuration.
- Does not block unexpired but revoked tokens unless the decoder/authorization adds extra mechanisms.

## 5. Resulting Authentication: JwtAuthenticationToken

With the payload from section 3 and the default converter, an authenticated `Authentication` has, for example:

| Method | Illustrative Value | Source |
| --- | --- | --- |
| `auth.getClass().getSimpleName()` | `JwtAuthenticationToken` | Converter output |
| `auth.isAuthenticated()` | `true` | Provider succeeded |
| `auth.getName()` | `user-42` | Default `sub` |
| `((JwtAuthenticationToken)auth).getToken().getSubject()` | `user-42` | Jwt subject |
| `auth.getAuthorities()` | `SCOPE_orders.read`, `SCOPE_orders.write` | From `scope` claim |
| `((JwtAuthenticationToken)auth).getTokenAttributes()` | Map of JWT claims | Verified token info |

By default, `JwtGrantedAuthoritiesConverter` reads `scope` or `scp`, splits whitespace-delimited scopes or handles collections as appropriate, and prepends `SCOPE_`.

```text
scope = "orders.read orders.write"
              |
              v
SCOPE_orders.read
SCOPE_orders.write

hasAuthority("SCOPE_orders.read")  -> may succeed
hasRole("ADMIN")                    -> not inferred
```

`getName()` can change via the converter, while `getToken().getSubject()` still reflects `sub`. For instance, `setPrincipalClaimName("preferred_username")` yields `"alice"` instead of `"user-42"`. For linking accounts across multi-issuer/multi-tenant systems, a stable `(iss,sub)` key is usually needed rather than mutable or reusable emails/display names.

**Successful Authentication does not imply successful Authorization.** A token with authority `SCOPE_orders.read` may allow calling the read endpoint, yet still must not read another user's order. Resource permissions (ownership/tenant/ACL) must be designed separately.

## 6. Configuring a Spring Boot API with a Real JwtDecoder

The following example targets **Spring Boot 3.x, Spring Security 6.x, and Java 17+**. The application requires access tokens issued by a trusted issuer; the `example.test` placeholder is illustrative only and must be replaced with a real IdP before running over a network.

### 6.1. Dependencies

In a Spring Boot Gradle project with the plugin, BOM, and JUnit Platform configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo

app:
  security:
    audience: orders-api
```

The issuer is preconfigured, not chosen dynamically from the `iss` declared by an unverified token.

### 6.2. Java Code

Create `src/main/java/example/JwtResourceApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {
        return http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Applies only to pure Bearer-header APIs that do not rely
            // on cookies to authenticate state-changing requests.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
                String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains(audience));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, correctAudience));
        return decoder;
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        return new JwtAuthenticationConverter();
    }
}

@RestController
class IdentityController {
    @GetMapping("/api/whoami")
    Map<String, Object> whoami(Authentication auth) {
        // Valid in this JWT-only Resource Server example.
        JwtAuthenticationToken jwt = (JwtAuthenticationToken) auth;

        List<String> authorities = jwt.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "type", jwt.getClass().getSimpleName(),
            "principalName", jwt.getName(),
            "subject", jwt.getToken().getSubject(),
            "authorities", authorities
        );
    }
}
```

**Note before running:** an authorization server with reachable discovery/JWKS and a properly signed access token with the right issuer/audience are required. When an app supports multiple authentication methods, the controller must check the Authentication type before casting; this example illustrates a single pure-JWT chain.

Explanation:

1. The `oauth2ResourceServer(...jwt(...))` DSL registers Bearer processing, decoder/provider, and filter-chain integration.
2. `NimbusJwtDecoder.withIssuerLocation(issuer)` uses issuer metadata and appropriate keys. `JwtValidators.createDefaultWithIssuer(issuer)` combined with a custom audience validator ensures issuer/time checks are not lost when calling `setJwtValidator`.
3. The default `JwtAuthenticationConverter` sets `getName()=sub` and `SCOPE_...`. The controller receives `JwtAuthenticationToken`, never directly decoding client-sent tokens.
4. `SessionCreationPolicy.STATELESS` avoids relying on `HttpSession` for API authentication. This differs from OIDC login using web sessions; tokens are verified per request.
5. Disabling CSRF in the example is appropriate only for APIs using Bearer headers without browser cookies as credentials. If sharing form/session flows, split security chains and retain appropriate CSRF policies.

Assuming a **real signed JWT** with claims `sub=user-42`, `scope=orders.read orders.write`, and `aud=["orders-api"]`, `GET /api/whoami` could return:

```json
{
  "type": "JwtAuthenticationToken",
  "principalName": "user-42",
  "subject": "user-42",
  "authorities": [
    "SCOPE_orders.read",
    "SCOPE_orders.write"
  ]
}
```

This is an **illustrative response matching those claims**, not output tested against `example.test`.

### 6.3. Custom Role and Username Claims

If a JWT from a trusted issuer contains:

```json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "roles": ["READER", "AUDITOR"]
}
```

You can **replace** the converter bean in section 6.2 with:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter roles =
        new JwtGrantedAuthoritiesConverter();
    roles.setAuthoritiesClaimName("roles");
    roles.setAuthorityPrefix("ROLE_");

    JwtAuthenticationConverter result =
        new JwtAuthenticationConverter();
    result.setPrincipalClaimName("preferred_username");
    result.setJwtGrantedAuthoritiesConverter(roles);
    return result;
}
```

Import `JwtGrantedAuthoritiesConverter` from `org.springframework.security.oauth2.server.resource.authentication`. The result will have `getName()="alice"` while `getToken().getSubject()="user-42"`; the authorities are `ROLE_READER` and `ROLE_AUDITOR`.

The customization above **replaces** the default scope mapping, so `SCOPE_orders.read` will no longer appear automatically if only the roles converter is used. To keep both scopes and roles, combine converters using `DelegatingJwtGrantedAuthoritiesConverter`, and inspect the claim structure carefully.

The converter **does not verify signatures or trust**. It only maps claims after the decoder has verified them per policy; never trust `roles` in a token from the wrong issuer or audience.

## 7. JUnit 5: Testing Real JwtAuthenticationProvider with a Fake JwtDecoder

The following unit test suite intentionally uses a **fake `JwtDecoder`** to test the exact **provider → converter → Authentication** relationship. A fake decoder does not verify JWT cryptography; these tests must not be used to claim production JWT signatures are safe.

Create `src/test/java/example/JwtProviderUnitTest.java`:

```java
package example;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtProviderUnitTest {

    private static Jwt exampleJwt() {
        Instant now = Instant.now();
        return Jwt.withTokenValue("example-token")
            .header("alg", "RS256")
            .claim("iss", "https://idp.example.test/realms/demo")
            .claim("sub", "user-42")
            .claim("preferred_username", "alice")
            .claim("scope", "orders.read orders.write")
            .claim("roles", List.of("AUDITOR"))
            .issuedAt(now.minusSeconds(10))
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    @Test
    void providerProducesJwtAuthenticationToken() {
        JwtDecoder fakeDecoder = raw -> {
            assertEquals("example-token", raw);
            return exampleJwt();
        };
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(fakeDecoder);

        Authentication auth = provider.authenticate(
            new BearerTokenAuthenticationToken("example-token"));

        JwtAuthenticationToken result =
            assertInstanceOf(JwtAuthenticationToken.class, auth);

        assertTrue(result.isAuthenticated());
        assertEquals("user-42", result.getName());
        assertEquals("user-42", result.getToken().getSubject());

        Set<String> names = result.getAuthorities().stream()
            .map(granted -> granted.getAuthority())
            .collect(Collectors.toSet());

        assertEquals(Set.of(
            "SCOPE_orders.read", "SCOPE_orders.write"), names);
    }

    @Test
    void decoderFailureDoesNotAuthenticate() {
        JwtDecoder rejectingDecoder = raw -> {
            throw new BadJwtException("rejected in unit test");
        };
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(rejectingDecoder);

        assertThrows(AuthenticationException.class, () ->
            provider.authenticate(
                new BearerTokenAuthenticationToken("invalid-token")));
    }

    @Test
    void customNameAndAuthoritiesCanDifferFromSubject() {
        JwtGrantedAuthoritiesConverter roles =
            new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");
        converter.setJwtGrantedAuthoritiesConverter(roles);

        JwtAuthenticationToken result =
            assertInstanceOf(JwtAuthenticationToken.class,
                converter.convert(exampleJwt()));

        assertEquals("alice", result.getName());
        assertEquals("user-42", result.getToken().getSubject());
        assertTrue(result.getAuthorities().contains(
            new SimpleGrantedAuthority("ROLE_AUDITOR")));
        assertFalse(result.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_orders.read")));
    }

    @Test
    void providerSupportsBearerNotPasswordAuthentication() {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(raw -> exampleJwt());

        assertTrue(provider.supports(
            BearerTokenAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
    }
}
```

Run in a project with the Gradle wrapper and dependencies above:

```bash
./gradlew test --tests "example.JwtProviderUnitTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.JwtProviderUnitTest"
```

The four test methods do not call `System.out.println`, so there is **no fixed business stdout**; Gradle/JUnit reports pass/fail per configuration. The strings inside `assertEquals` are the verification expectations. This test code is independent of an IdP, but it **does not execute a real decoder**.

## 8. How Real JWT Testing Differs from MockMvc jwt()

In Spring Security Test, `SecurityMockMvcRequestPostProcessors.jwt()` attaches a simulated JWT Authentication to a request. Using it to test controllers or authorization is appropriate; **it does not prove `JwtDecoder` verified signature, issuer, or audience**.

Illustrative test method placed in a `@SpringBootTest`/`@AutoConfigureMockMvc` class that has `MockMvc mvc` and an existing `GET /api/orders/{id}` endpoint:

```java
@Test
void scopeReadAllowsGetButNotWrite() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());

    mvc.perform(post("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isForbidden());
}
```

This is a **snippet**, requiring imports for `jwt`, `get`, `post`, `status`, `SimpleGrantedAuthority`, and the corresponding endpoints/handlers. It is not a standalone runnable program.

To test a real decoder, generate a JWT **signed with a test key**, configure `NimbusJwtDecoder` with a test public key or JWK Set, and send it via a real HTTP header to the Resource Server. Test at least:

| Case | Expectation |
| --- | --- |
| JWT with valid signature/issuer/audience/expiration | Decoder accepts; converter creates Authentication; authorization checks permissions |
| Signature does not match trusted key | Authentication fails; typically 401 |
| Disallowed `alg` | Reject JWT |
| Wrong `iss` despite valid signing key | Reject JWT |
| `aud` missing API despite valid `iss` | Reject JWT, if audience validator is configured |
| Expired `exp` or not-yet-valid `nbf` | Reject JWT |
| Valid token lacking `SCOPE_orders.read` | Authentication succeeds, authorization denies; typically 403 |
| Token with scope, resource belongs to another user/tenant | Denied by business ACL |
| JWK endpoint error/timeout | Fail closed, never grant access just because signature cannot be checked |
| Token using `scope` vs. `scp`, or custom roles claim | Converter must produce expected authorities per policy |

**401 vs. 403:** 401 typically indicates missing or invalid authentication credentials; 403 typically means credentials were accepted but permissions are insufficient. In environments with custom gateways or entrypoints, test actual status codes rather than guessing from exception classes.

## 9. Ten Common Mistakes When Wiring JwtDecoder and JwtAuthenticationProvider

1. **Parsing the payload manually and setting `SecurityContextHolder`.** An attacker can forge `role` if the app skips signature verification. Use a real decoder and validators.
2. **Trusting a token just because the JWT is validly signed.** The token might belong to another resource. Verify `iss`, `aud`, token type, and client policies.
3. **Sending an OIDC ID token to an API.** ID tokens have an audience for the OIDC client; APIs need access tokens for their own resource.
4. **Overwriting validators.** Calling `setJwtValidator` with only an audience validator can accidentally drop issuer/time checks. Combine properly with default validators.
5. **Using `roles` expecting automatic role mapping.** The default maps `scope`/`scp` to `SCOPE_`. Configure a dedicated converter for `ROLE_`.
6. **Changing `getName()` to email and treating email as an immutable ID.** Use `(iss,sub)` or a stable business identifier.
7. **Treating successful Authentication as permission for every operation.** Enforce endpoint, scope, and per-resource ownership authorization.
8. **Logging raw tokens.** Never log the `Authorization` header or `Jwt.getTokenValue()` because it is a bearer credential.
9. **Testing only with `jwt()` or fake decoders and concluding cryptography is safe.** Add tests through a real decoder with real signed and invalid tokens.
10. **Confusing Servlet with Reactive.** Servlet uses `JwtAuthenticationProvider`/`JwtDecoder`; WebFlux uses `JwtReactiveAuthenticationManager`/`ReactiveJwtDecoder`. Filter chain configurations differ.

Additionally, passing Bearer tokens via query parameters risks exposure in logs, referrers, and browser history; prefer the `Authorization` header over HTTPS. Running the API in stateless mode does not replace JWT verification or per-resource permission checks.

## 10. Completion Checklist

- [ ] Understand the chain `BearerTokenAuthenticationFilter → BearerTokenAuthenticationToken → JwtAuthenticationProvider → JwtDecoder → JwtAuthenticationConverter → JwtAuthenticationToken`.
- [ ] Decoder uses trusted keys/algorithms and enforces `iss`, `exp`, `nbf`, `aud`, and corresponding token profile validators.
- [ ] Invalid tokens are rejected before a successful `Authentication` is created.
- [ ] `getName()`, `getToken().getSubject()`, and `getAuthorities()` reflect the chosen claims and converter.
- [ ] Authorize via scopes/authorities and check data by user/tenant, not merely `isAuthenticated()`.
- [ ] Resource Server rejects ID tokens, opaque tokens, or tokens issued for other APIs lacking appropriate verification.
- [ ] Test provider/converter with a fake decoder **and** test real verification with real signed tokens for invalid signature/issuer/audience/expiry cases.
- [ ] Do not log credentials, and do not rely on old sessions to skip verifying new tokens.

## 11. Official Documentation

- Spring Security — Resource Server JWT (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Resource Server Overview: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security API — `JwtAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html
- Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security API — `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security — OAuth2 Resource Server Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- RFC 6750 — Bearer Token Usage: https://datatracker.ietf.org/doc/html/rfc6750
- RFC 9068 — JWT Profile for Access Tokens: https://datatracker.ietf.org/doc/html/rfc9068
