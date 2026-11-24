# Audience, Issuer, and Preconditions Before Using Claims to Grant Authorities

> **Topic:** Spring Security – authorization → **Authorities from OAuth2**. This lesson clarifies how an OAuth2 Resource Server decides whether a JWT access token is **trustworthy enough to read permissions from**: verifying signature and algorithm, issuer (`iss`), audience (`aud`), timestamps (`exp`/`nbf`), **token type** (`typ`), client, and required claims before mapping `scope`/`scp`/`roles` into Spring Security authorities. Includes threat modeling, Spring Security 6.x/Boot 3.x configuration, a Java 17+ demo with real RSA-signed JWTs in tests, 401/403 testing, multi-tenancy notes, opaque tokens, troubleshooting, and exercises.

## 1. Principle: claims matter only after the token is accepted for the right API

A JWT looks like:

~~~text
header.payload.signature
~~~

Merely being able to Base64URL-decode `payload` and see:

~~~json
{
  "iss": "https://login.example.invalid/realms/demo",
  "aud": ["urn:ledger-api"],
  "sub": "alice",
  "scope": "ledger.read ledger.write",
  "exp": 1924992000
}
~~~

**does not mean** the user has permission to read or edit the ledger. At the decode step, the JWT payload is **sender-supplied data**; until signature and token-usage constraints are verified, every `scope`/`roles`/`tenant` is purely self-asserted.

A correct decision has **two gates**, in order:

~~~text
Authorization: Bearer <token>
               |
               v
GATE A: TOKEN VALIDATION / AUTHENTICATION
 - valid format and token type?
 - valid signature with public key from trusted issuer?
 - algorithm in allowlist?
 - exact issuer?
 - audience includes this resource API?
 - valid exp, nbf, iat, and required claims?
 - client/grant/tenant per profile if applicable?
               |
       FAIL --> 401 invalid_token
               |
              PASS
               v
GATE B: AUTHORIZATION
 - scope/roles claims mapped accurately?
 - which authority does the operation require?
 - does subject have access to the exact tenant/object?
 - do current membership/entitlements allow it?
               |
       FAIL --> 403 insufficient_scope/forbidden
               |
              PASS
               v
          BUSINESS OPERATION
~~~

**Never execute Gate B by parsing claims from a token that has not passed Gate A.** An access token with powerful scopes issued for *another API* must be rejected at audience validation before authorization runs.

## 2. Distinguishing OAuth2 access token, ID token, and JWT

| Term | What is it for? | Intended recipient |
| --- | --- | --- |
| **OAuth2 access token** | Credential delegating resource access | Resource Server/API (`aud` targets API) |
| **OIDC ID token** | Asserts authentication event and user identity to client | Relying party/OIDC client (`aud` is typically client ID) |
| **Refresh token** | Used with Authorization Server to obtain new access tokens | Authorization Server; never send directly to APIs |
| **JWT** | A token format (JWS/JWE), usable for multiple purposes | Cannot tell purpose just by seeing three segments |
| **Opaque access token** | Reference string without locally readable claims | Resource Server typically introspects via trusted endpoint |

**JWT does not automatically mean OAuth2 access token.** A validly signed token may still be an **ID token**, logout token, or token intended for a different service. Reusing the wrong token type is called **token substitution / token confusion**.

Under the **RFC 9068** JWT access token profile, `typ` in the JOSE header must be `at+jwt` or `application/at+jwt` when the resource server validates tokens against that profile. Do not rely solely on seeing a `scope` or `sub` field.

### 2.1. A well-targeted illustrative token

~~~json
{
  "header": {
    "alg": "RS256",
    "typ": "at+jwt",
    "kid": "training-key-1"
  },
  "claims": {
    "iss": "https://issuer.example.invalid/tenant-a",
    "sub": "user-17",
    "aud": ["urn:ledger-api"],
    "client_id": "console-client",
    "scope": "ledger.read",
    "iat": 1910000000,
    "nbf": 1910000000,
    "exp": 1910000300,
    "jti": "token-001"
  }
}
~~~

This is an **illustrative structure**, not a real compact JWT and without a real signature. Timestamps merely illustrate `iat/nbf/exp` relationships; never use sample tokens in production requests. In the runnable tests later, `iat` and `exp` are computed dynamically around the current time.

### 2.2. Claims do not replace business checks

Even after a JWT is valid:

~~~text
Token: sub=alice, aud=ledger-api, scope=ledger.read
Request: GET /api/tenants/beta/ledger/202
Membership DB: alice belongs to tenant acme
Resource DB: ledger#202 belongs to beta
=> DENY
~~~

`scope=ledger.read` proves the token was granted this permission class **within the semantics agreed between the Authorization Server and API**; it does not grant access to every record or every tenant.

## 3. Checking `iss`: who issued the token?

`iss` (issuer) identifies the entity that issued the JWT. In OAuth2, the Resource Server must maintain a **set of trusted issuers** from configuration/governance, rather than trusting whatever URL the JWT declares.

Example expected API configuration:

~~~text
TRUSTED_ISSUER=https://issuer.example.invalid/tenant-a
~~~

| `iss` in JWT | Result |
| --- | --- |
| `https://issuer.example.invalid/tenant-a` | Matches issuer condition |
| `https://issuer.example.invalid/tenant-b` | DENY: issuer from another tenant |
| `https://issuer.example.invalid/tenant-a/` | Mismatch if canonical issuer lacks trailing slash |
| `http://issuer.example.invalid/tenant-a` | Protocol mismatch |
| `https://issuer.example.invalid/tenant-A` | Case mismatch |
| Missing `iss` | DENY under profiles requiring issuer |

The issuer identifier must be compared strictly against the configured identifier, **never** with `contains("example.invalid")`, `startsWith(...)`, or domain comparisons after stripping segments. When an API trusts multiple issuers, decoder/public-key selection must come from an **issuer allow-list**.

### 3.1. Issuer and discovery/JWKS

Authorization Servers typically publish OAuth2 Authorization Server Metadata or OpenID Connect Discovery:

~~~text
Known issuer
    |
    v
Trusted metadata endpoint
    |
    v
JWK Set URI published by trusted metadata
    |
    v
Verifier fetches public keys + supported algorithms
    |
    v
Token signature + iss validation
~~~

The Resource Server must trust the **pair** of issuer and key set, not merely accept a token with a plausible-looking issuer string. An `iss` inside an **unverified** JWT cannot dictate where the API fetches keys from.

**Severe risk:** code that reads `iss` from a token and calls `JwtDecoders.fromIssuerLocation(iss)` for any client-supplied issuer can allow an attacker's issuer to mint accepted tokens. Multi-issuer models must verify the issuer against a trusted list before constructing a decoder for that issuer. This also prevents SSRF against unapproved metadata URLs.

### 3.2. Across environments

`dev`, `staging`, and `production` usually use different issuers. Never build a validator saying "accept if issuer contains company domain" so dev tokens work in production. Each environment needs distinct issuer, audience, algorithm, and trust material configs; write tests to reject tokens from other environments.

### 3.3. Tenant ID is not synonymous with issuer

An organization might have:
- One issuer serving multiple tenants, with tenant carried in membership or a dedicated claim.
- One issuer per tenant.
- One API trusting a set of issuers.

Whichever model applies, a valid `iss` proves only who issued the token, **not** that the caller belongs to the tenant in the URL. Tenant claims/membership and resource ownership still need independent enforcement.

## 4. Checking `aud`: which resource server is this token for?

`aud` (audience) identifies intended recipients of the token. For JWT access tokens, the Resource Server must verify that audience includes **this API's identifier**.

Example:

~~~text
Ledger API expects: urn:ledger-api
Reports API expects: urn:reports-api
Portal client ID:    console-client
~~~

Alice may hold a token:

~~~json
{
  "iss": "https://issuer.example.invalid/tenant-a",
  "aud": ["urn:reports-api"],
  "scope": "ledger.read reports.read"
}
~~~

Even though it contains `ledger.read`, the Ledger API must **reject** it because the token targets Reports API, not Ledger API.

### 4.1. Audience is not client ID

| Claim | Question |
| --- | --- |
| `aud` | Which Resource Server/API may accept this token? |
| `client_id` | Which OAuth2 client received/was issued the access token? |
| `azp` | Authorized party per the token/profile semantics |
| `sub` | Subject of the token per grant/profile |
| `scope`/`scp` | Delegated permissions per API/AS contract |

An OIDC ID token has `aud=console-client` and may carry `roles` for the UI. Ledger API must not accept it as an access token simply because both the ID token and access token were signed by the same identity provider.

### 4.2. `aud` as string or array

JWT allows audience to be a JSON string or array; Spring Security's API typically exposes it via `Jwt.getAudience()` as a list.

~~~json
{"aud":"urn:ledger-api"}
~~~

Or:

~~~json
{"aud":["urn:reports-api","urn:ledger-api"]}
~~~

With the rule `aud contains urn:ledger-api`, both forms can be valid per contract. **Never** write `jwt.getClaimAsString("aud").equals(...)` assuming every issuer always sends a string; and never do substring matches like `aud.toString().contains("ledger")`.

A stricter policy (requiring a single audience only) can be added, but must be agreed with the issuer/clients and explicitly tested. RFC 9068 requires audience to contain the resource indicator of the receiving resource server.

### 4.3. Why multiple audiences require caution

A token with broader audiences increases replay exposure if multiple APIs interpret identical scope names similarly. Consider:
- Issuing narrow-audience access tokens per resource.
- Using resource indicators per RFC 8707 when supported by the Authorization Server.
- Designing clearly namespaced scopes (`ledger.read`, `reports.read`).
- Never calling API B with API A's token simply by forwarding the header.
- Using proper token exchange/on-behalf-of protocols when downstream calls need a different audience.

**Takeaway:** checking issuer without audience still lets a real token issued for **another service** slip through.

## 5. Before trusting claims, verify signature, algorithm, and key source

A JWT JWS consists of:

~~~text
base64url(header) . base64url(payload) . base64url(signature)
~~~

With `RS256`, the signature is generated using RSA + SHA-256, and the resource server verifies it with the issuer's **trusted public key**. Base64URL decoding, JSON parsing, or calling `Jwt.getClaim(...)` on a manually constructed object **does not verify** the signature.

### 5.1. Minimum checks

1. JWT is well-formed with bounded size, header, and JSON.
2. `alg` must be in the trusted issuer/API allow-list; **reject `none`** and unsupported algorithms.
3. `kid` is only a **key selection hint** inside the trusted JWK Set, not proof that the key is trustworthy.
4. Public keys come from trusted issuer metadata/JWKS or configured key pinning.
5. Verify the signature using the matching algorithm and key type.
6. Only afterward evaluate `iss`, `aud`, `exp`, `nbf`, `typ`, and other claims.
7. Only upon passing validation map authorities and check permissions.

Never load arbitrary `jku`, `x5u`, or key URLs from a client-supplied token header. Never "auto-learn" a public key from an unverified token. A `kid` missing from the trusted JWK Set must trigger a verification failure or a controlled key-refresh workflow, **never** fetching arbitrary keys from the internet.

### 5.2. Key rotation

When an Authorization Server rotates keys, JWKS may publish the new key while keeping the old key during a transition window. The Resource Server needs reliable JWKS refresh/caching/timeout handling, failing closed if signatures cannot be verified. Never disable signature validation during identity provider downtime.

### 5.3. Symmetric vs. asymmetric

With `HS256`, the Resource Server must hold the shared secret to verify. With `RS256`/`ES256`, the Resource Server needs only the public key, avoiding distribution of private signing material. Per RFC 9068, asymmetric signatures are recommended for access tokens. The runnable example below uses a **test RSA keypair** and shares only the public key with the decoder.

## 6. Timestamps, token type, and required claims

| Field | Meaning | Verification |
| --- | --- | --- |
| `exp` | Token expiration time | Now must be before `exp` (with small bounded clock skew) |
| `nbf` | Not-before | Reject if presented too early |
| `iat` | Issued-at | Valid per profile, reject absurd `iat`, useful in telemetry |
| `jti` | JWT ID | Usable for replay/revocation tracking per policy |
| `typ` (JOSE header) | Token type | RFC 9068 requires `at+jwt` or `application/at+jwt` |
| `iss` | Issuer | Exact match against trusted issuer |
| `aud` | Audience | Includes this API |
| `client_id` | OAuth2 client ID | Check if required by policy/resource profile |
| `sub` | Subject | Present and interpreted accurately |
| `scope` | Delegated scopes | Used only after validation and per API policy |

RFC 9068 defines a profile with required claims including `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, and `jti`; `nbf` may also appear. Issuers not following that profile may differ structurally, so **define an explicit contract**. Never attach an RFC 9068 validator to an issuer using a different format and then strip rules until tests pass.

### 6.1. Clock skew is not "unlimited extension"

Spring Security's `JwtTimestampValidator` applies bounded clock skew to tolerate minor clock drift across hosts. Tens of seconds or a couple minutes may be reasonable depending on infrastructure; never configure hours of skew that keep expired tokens valid.

Tests should use tokens expired **clearly beyond clock skew**, rather than testing right on the boundary where a few seconds of slowness make tests flaky.

### 6.2. `typ` to prevent token confusion

An OIDC ID token typically has `typ=JWT` or no required type matching the access-token profile. An RFC 9068-compliant Resource Server must require `at+jwt`; seeing `roles` inside an ID token and accepting it as an access token is wrong. In Spring Security **6.5**, the explicit configuration recommended by official docs is:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuerUri)
        .validateType(false)
        .build();

decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
                .issuer(issuerUri)
                .audience("urn:ledger-api")
                .clientId("console-client")
                .build());
~~~

This is an **integration snippet**; `issuerUri` must come from trusted config. `validateType(false)` disables Nimbus's default type check and **delegates type verification to `createAtJwtValidator()`**; it does not mean "disable type protection completely." This API exists in Spring Security 6.5; when upgrading to 7.x, re-verify default `typ`/validator handling.

## 7. Gate A vs. Gate B: deciding 401 vs. 403

Once the token is validated, Spring Resource Server maps `scope`/`scp` claims into authorities like `SCOPE_ledger.read` by default.

| Scenario | Authentication/validation | Authorization | Typical HTTP |
| --- | --- | --- | --- |
| Missing token | Unauthenticated | Not evaluated | 401 |
| Bad signature | FAIL | Scope not evaluated | 401 |
| Wrong `iss` | FAIL | Scope not evaluated | 401 |
| `aud` omits API | FAIL | Scope not evaluated | 401 |
| `typ` does not match required access token profile | FAIL | Scope not evaluated | 401 |
| `exp` in the past | FAIL | Scope not evaluated | 401 |
| Valid token lacking `ledger.read` | PASS | DENY | 403 |
| Valid token with `ledger.read` | PASS | ALLOW on read endpoint | 200 if business succeeds |
| Valid token with scope, object in another tenant | PASS | DENY object scope | 403/404 per API policy |

Systems can customize error responses, yet the logical boundary between **invalid token** and **valid token with insufficient permissions** must stay clear. Never return sensitive data or raw claims in 401/403 responses.

## 8. Configuring Spring Boot Resource Server for production

This lesson uses **Servlet Spring MVC** to write real integration tests with `MockMvc`. If your application uses WebFlux, switch to `ServerHttpSecurity` and `ReactiveJwtDecoder` accordingly; never mix the two stacks.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Spring Boot resource server starter provides the dependencies needed to verify JWT/JWS. For non-Boot apps, include `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose`.

### 8.2. Configure both issuer and audience—never omit one arbitrarily

Production example with a real operating issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/prod
          audiences:
            - urn:ledger-api
~~~

In supported Spring Boot 3.x versions, `spring.security.oauth2.resourceserver.jwt.audiences` specifies the expected API audience. `issuer-uri` enables issuer verification and metadata/JWKS discovery (depending on configuration).

**Note:** `https://idp.example.com/realms/prod` is an illustrative address; replace it with your real issuer and confirm the exact issuer identifier in your IdP documentation. Do not configure an IdP lacking reachable metadata in the runtime environment.

### 8.3. When using an explicit decoder

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuerUri)
            .build();
    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuerUri),
                    new JwtAudienceValidator("urn:ledger-api")));
    return decoder;
}
~~~

Imports:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtAudienceValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

**This is an integration snippet, not runnable standalone:** `issuerUri` must come from a trusted configuration source. When declaring a custom `JwtDecoder` bean, you are responsible for combining all required issuer/audience/time/type validators; do not assume Boot auto-config properties are still applied automatically to a custom decoder. Never call `setJwtValidator(customAudienceOnly)` and accidentally drop timestamp/issuer validators.

**Important:** the decoder above uses the default JWT type contract. If the issuer emits **RFC 9068 `at+jwt`**, use `validateType(false)` + `JwtValidators.createAtJwtValidator()` as shown in Section 6.2 and the demo below, rather than copying config meant for a different JWT type.

### 8.4. Validate JWT first, then check scopes

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/ping").permitAll()
                    .requestMatchers(
                            HttpMethod.GET, "/api/ledger/**")
                    .hasAuthority("SCOPE_ledger.read")
                    .requestMatchers(
                            HttpMethod.POST, "/api/ledger/**")
                    .hasAuthority("SCOPE_ledger.write")
                    .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
}
~~~

Key imports:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
~~~

`csrf.disable()` here **only** illustrates a stateless API **using Bearer tokens solely in the Authorization header**, without browser-automatic cookies or Basic auth. If a filter chain also uses cookie/session credentials, evaluate CSRF instead of disabling it unconditionally.

## 9. Self-contained demo: Spring Boot 3.5.x with real RSA-signed JWTs in tests

This main exercise makes no internet calls to an external IdP: the app generates an **ephemeral in-memory RSA keypair when tests start**, the decoder uses the public key and checks `iss`, `aud`, `typ`, `client_id`, timestamps, and required claims per RFC 9068. Tests sign real JWTs with the matching private key and send them via `Authorization: Bearer` to `MockMvc`.

**Goal:** avoid the blind spot of `spring-security-test`'s `mockJwt()`. `mockJwt()` is great for testing `hasAuthority` rules, yet it **does not prove** signature, issuer, audience, or decoder validation works because it injects a mock `Authentication` and bypasses real token decoding.

### 9.1. `settings.gradle`

~~~groovy
rootProject.name = 'oauth2-jwt-trust-lab'
~~~

### 9.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.jwttrust'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.3. `src/main/java/demo/jwttrust/JwtTrustApplication.java`

~~~java
package demo.jwttrust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtTrustApplication.class, args);
    }
}
~~~

### 9.4. `src/main/java/demo/jwttrust/ResourceServerSecurity.java`

~~~java
package demo.jwttrust;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ResourceServerSecurity {

    public static final String ISSUER =
            "https://issuer.example.invalid/tenant-a";
    public static final String AUDIENCE = "urn:ledger-api";
    public static final String CLIENT_ID = "console-client";

    @Bean
    KeyPair demoSigningKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtDecoder jwtDecoder(KeyPair demoSigningKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(
                        (RSAPublicKey) demoSigningKeyPair.getPublic())
                .validateType(false)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(AUDIENCE)
                        .clientId(CLIENT_ID)
                        .build());
        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/ledger/entries")
                        .hasAuthority("SCOPE_ledger.read")
                        .requestMatchers(
                                HttpMethod.POST, "/api/ledger/entries")
                        .hasAuthority("SCOPE_ledger.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                // Only because the demo is a stateless Bearer-header API.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

**Reading the configuration:**

1. `demoSigningKeyPair` is strictly for learning/test environments. **Never generate private signing keys inside a production resource server.** In real systems, the Authorization Server holds the private key, while the Resource Server obtains public JWKs via a trusted issuer.
2. `withPublicKey` trusts only the RSA public key injected from the bean; it never fetches keys from a URL declared inside a JWT.
3. `validateType(false)` delegates `typ` verification to `createAtJwtValidator()` so RFC 9068 JWT access tokens are required instead of the default JWT type.
4. The validator enforces issuer, audience, client ID, and RFC 9068 rules; tests deliberately send validly signed tokens with wrong `iss`/`aud`/`typ`.
5. URL authorization requires `SCOPE_ledger.read` for `GET` and `SCOPE_ledger.write` for `POST`, never conflating the two actions.
6. `jwtDecoder` is invoked by Spring Resource Server to validate the bearer token **before** scopes are mapped into authorities.
7. No custom `JwtAuthenticationConverter` is needed because default `scope` mapping fits this lesson.
8. `anyRequest().denyAll()` locks down undefined routes.
9. `example.invalid` is a documentation-only domain; the app skips metadata discovery because it uses the public key directly. Never copy this issuer into production.

### 9.5. `src/main/java/demo/jwttrust/LedgerController.java`

~~~java
package demo.jwttrust;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LedgerController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/ledger/entries")
    public String read(Principal principal) {
        return "read:" + principal.getName();
    }

    @PostMapping("/api/ledger/entries")
    public String write(Principal principal) {
        return "write:" + principal.getName();
    }
}
~~~

The controller deliberately never touches raw JWTs or parses scopes manually. Spring Security authenticates and builds `Authentication`; rules are enforced **before the controller receives the request**. The controller returns only a demo string. In production, the service must still verify owner/tenant/resource permissions and authorization for side effects.

## 10. Integration tests: real signed JWTs without using `mockJwt` to bypass Gate A

The tests:
- Construct JWT access token claims with `iss`/`sub`/`aud`/`client_id`/`iat`/`jti`/`exp`/`scope`.
- JSON-serialize header/payload and Base64URL-encode them.
- Sign with the **test fixture's** RSA private key using `SHA256withRSA` (JWT `RS256`).
- Send the real compact JWT in `Authorization: Bearer`.
- Let MockMvc run the Spring Security filter chain so `NimbusJwtDecoder` checks the signature and validators.
- Test 401 invalid tokens separately from 403 valid tokens lacking authorities.

### 10.1. `src/test/java/demo/jwttrust/TokenTrustIntegrationTest.java`

~~~java
package demo.jwttrust;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = JwtTrustApplication.class)
@AutoConfigureMockMvc
class TokenTrustIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired KeyPair demoSigningKeyPair;
    @Autowired ObjectMapper mapper;

    private static String b64(byte[] bytes) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    private Map<String, Object> standardClaims() {
        long now = Instant.now().getEpochSecond();
        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("iss", ResourceServerSecurity.ISSUER);
        claims.put("sub", "alice");
        claims.put("aud", List.of(ResourceServerSecurity.AUDIENCE));
        claims.put("client_id", ResourceServerSecurity.CLIENT_ID);
        claims.put("scope", "ledger.read");
        claims.put("iat", now - 10);
        claims.put("nbf", now - 10);
        claims.put("exp", now + 300);
        claims.put("jti", UUID.randomUUID().toString());
        return claims;
    }

    private String sign(
            Map<String, Object> claims,
            PrivateKey privateKey,
            String tokenType) throws Exception {

        Map<String, Object> header = Map.of(
                "alg", "RS256",
                "typ", tokenType);

        String signingInput =
                b64(mapper.writeValueAsBytes(header)) + "."
                + b64(mapper.writeValueAsBytes(claims));

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(
                signingInput.getBytes(StandardCharsets.US_ASCII));

        return signingInput + "." + b64(signature.sign());
    }

    private String token(Map<String, Object> claims)
            throws Exception {
        return sign(
                claims,
                demoSigningKeyPair.getPrivate(),
                "at+jwt");
    }

    private ResultActions readWith(String compactJwt)
            throws Exception {
        return mvc.perform(get("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + compactJwt));
    }

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void missingBearerTokenIs401() throws Exception {
        mvc.perform(get("/api/ledger/entries"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctIssuerAudienceSignatureTypeAndScopeAreAccepted()
            throws Exception {

        readWith(token(standardClaims()))
                .andExpect(status().isOk())
                .andExpect(content().string("read:alice"));
    }

    @Test
    void issuerFromAnotherTenantRejectedDespiteValidSignature()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("iss",
                "https://issuer.example.invalid/tenant-b");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceRejectedDespiteValidReadScope()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("aud", List.of("urn:reports-api"));

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingAudienceIsInvalid()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.remove("aud");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void multipleAudiencesIncludingThisApiAreAccepted()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("aud",
                List.of("urn:reports-api",
                        ResourceServerSecurity.AUDIENCE));

        readWith(token(claims))
                .andExpect(status().isOk());
    }

    @Test
    void tokenWithOrdinaryJwtTypeIsNotAtJwt()
            throws Exception {

        String ordinaryJwt = sign(
                standardClaims(),
                demoSigningKeyPair.getPrivate(),
                "JWT");

        readWith(ordinaryJwt)
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongClientIdIsDeniedByThisApiPolicy()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("client_id", "different-client");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        long now = Instant.now().getEpochSecond();
        claims.put("exp", now - 3600);

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void futureNotBeforeIsRejected()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        long now = Instant.now().getEpochSecond();
        claims.put("nbf", now + 3600);

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void untrustedSignatureIsRejected()
            throws Exception {

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrustedKey = generator.generateKeyPair();

        String forged = sign(
                standardClaims(),
                untrustedKey.getPrivate(),
                "at+jwt");

        readWith(forged)
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenWithoutRequiredReadScopeIs403()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("scope", "ledger.write");

        readWith(token(claims))
                .andExpect(status().isForbidden());
    }

    @Test
    void validReadTokenDoesNotGrantWrite()
            throws Exception {

        mvc.perform(post("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token(standardClaims())))
                .andExpect(status().isForbidden());
    }

    @Test
    void validWriteTokenIsAcceptedForWrite()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("scope", "ledger.write");

        mvc.perform(post("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token(claims)))
                .andExpect(status().isOk())
                .andExpect(content().string("write:alice"));
    }
}
~~~

**Testing note:** Java `Signature` with `SHA256withRSA` performs JWS `RS256` signing. Because tests use an **ephemeral** private key, every valid test signature belongs to the bean-provided keypair; the code **does not** demonstrate obtaining private keys from a production IdP. One test uses an untrusted key to prove the decoder actually verifies signatures.

### 10.2. Result matrix

| Case | Signature | `iss` | `aud` | `typ` | Scope | HTTP |
| --- | --- | --- | --- | --- | --- | --- |
| No token | — | — | — | — | — | 401 |
| Valid token | OK | Valid | Contains API | at+jwt | ledger.read | 200 |
| Another tenant's issuer | OK | Wrong | Valid | at+jwt | ledger.read | 401 |
| `reports-api` audience | OK | Valid | Wrong | at+jwt | ledger.read | 401 |
| Missing audience | OK | Valid | Missing | at+jwt | ledger.read | 401 |
| Audience includes `reports-api` + `ledger-api` | OK | Valid | Contains API | at+jwt | ledger.read | 200 |
| Ordinary `typ` JWT | OK | Valid | Valid | JWT | ledger.read | 401 |
| Disallowed Client ID | OK | Valid | Valid | at+jwt | ledger.read | 401 |
| Expired token | OK | Valid | Valid | at+jwt | ledger.read | 401 |
| Token before `nbf` | OK | Valid | Valid | at+jwt | ledger.read | 401 |
| Signed with different RSA key | INVALID | Valid | Valid | at+jwt | ledger.read | 401 |
| Valid token missing read scope | OK | Valid | Valid | at+jwt | ledger.write | 403 |
| Valid read token calling POST | OK | Valid | Valid | at+jwt | ledger.read | 403 |
| Valid write token calling POST | OK | Valid | Valid | at+jwt | ledger.write | 200 |

**Two key lessons:** (1) A strong scope cannot rescue a token with the wrong issuer, audience, or signature. (2) A validly authenticated token does not mean every operation is permitted.

### 10.3. Run commands

~~~bash
./gradlew test --tests demo.jwttrust.TokenTrustIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.jwttrust.TokenTrustIntegrationTest
gradlew.bat bootRun
~~~

Tests do not need network access to `issuer.example.invalid` because the decoder pins the public key from the bean and validates the issuer string locally. Tests generate RSA-signed tokens in memory; there is no fixed business stdout. **Expected outcome** is passing assertions and Gradle completing the `test` task; the sample code has been statically checked and should be run in an appropriate Gradle/JDK environment before serving as a production baseline.

## 11. Demo limitations and real-world deployment

### 11.1. Never generate signing keys inside a production Resource Server

The demo app has:

~~~java
@Bean
KeyPair demoSigningKeyPair() {
    // Generate key pair for local test ...
}
~~~

This is strictly a test fixture. In production, **private keys belong to the Authorization Server**; the Resource Server retrieves public keys from trusted issuer metadata/JWKS or pins them via configuration. If an API holds private signing keys like an Authorization Server without explicit governance justification, the trust boundary expands unnecessarily.

### 11.2. Client ID policy must fit reality

`createAtJwtValidator().clientId("console-client")` in the demo intentionally accepts tokens issued to **one client**. Many production APIs legitimately serve **multiple OAuth clients**. Design a client-ID allow-list, client classification, or profile-specific validator accordingly; never hardcode one fixed client unless the business contract requires it.

However, never drop `aud` or `iss` just to accept tokens from multiple clients. **Audience identifies the target resource**, not the calling OAuth client.

### 11.3. The demo does not cover every business condition

Even a valid access token still requires evaluating:
- Resource ownership, tenant membership, account status, and action policies.
- Revocation of roles/entitlements or tokens before token expiration.
- Object restrictions per scopes and permission catalogs.
- Delegation/on-behalf-of: who the user is vs. who the service client is.
- Rate limiting and DPoP/mTLS proof-of-possession if required by the system.
- Logging and auditing without recording raw tokens, private keys, or excessive personal data.

## 12. Reading scopes and roles after Gate A passes

By default, Spring Security Resource Server maps `scope` or `scp` into authorities prefixed with `SCOPE_`:

~~~text
JWT claim: "scope": "ledger.read ledger.write"
Authorities:
  SCOPE_ledger.read
  SCOPE_ledger.write
~~~

Rules:

~~~java
.requestMatchers(HttpMethod.GET, "/api/ledger/**")
    .hasAuthority("SCOPE_ledger.read")
.requestMatchers(HttpMethod.POST, "/api/ledger/**")
    .hasAuthority("SCOPE_ledger.write")
~~~

**Do not confuse:**
- `scope=ledger.read` does not automatically become `ROLE_ADMIN`.
- Custom `roles` claims are not mapped like `scope` without a configured converter.
- `hasRole("ADMIN")` checks `ROLE_ADMIN` by default; `hasAuthority("SCOPE_ledger.read")` checks the exact string.
- One issuer may send `scp` as an array while another sends `scope` as a string; always check the real claim contract.
- Scopes granted at the Authorization Server do not replace permissions on individual resources or tenants.

### 12.1. Converters must never grant authorities before validation

If the IdP emits a custom `roles` claim:

~~~json
{
  "roles": ["TENANT_ADMIN"]
}
~~~

you can build a `JwtAuthenticationConverter` and `Converter<Jwt, Collection<GrantedAuthority>>` to add authorities against an allow-list. Yet the converter must run on a `Jwt` already verified by `JwtDecoder`; never parse raw JWTs with Jackson and push authorities into `SecurityContext` manually.

Also bind roles to tenants. `TENANT_ADMIN` in tenant A is not platform-wide admin; enforce membership and domain policies server-side.

### 12.2. Separate authorization for service-to-service calls

In the client credentials grant, `sub` may not represent an end user with the same semantics as the authorization code grant. The API must know how to handle `client_id`/subject/service identity rather than assuming every token represents an interactive user.

Define dedicated permissions for service accounts instead of giving `SYSTEM_ADMIN` to every job; audits must distinguish the initiating user from the service client when delegation is used.

## 13. Multi-tenant and multi-issuer: avoid selecting validators from untrusted issuers

For example, an API serving two trusted issuers:

~~~text
ALLOWED_ISSUERS:
  https://idp.example.invalid/tenant-a
  https://idp.example.invalid/tenant-b
~~~

Spring Security Servlet supports this pattern:

~~~java
// INTEGRATION SNIPPET (requires corresponding imports and HttpSecurity config)
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.invalid/tenant-a",
                "https://idp.example.invalid/tenant-b");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

**For trust policy illustration only, not a standalone app:** the two sample issuers have no real metadata. The resolver inspects the issuer claim to select a strategy, yet **accepts only issuers in the allow-list**; each selected strategy must still verify signatures and JWT validators.

For multi-tenant production:
1. Source allowed issuers from an admin-managed trust repository, never from request bodies.
2. Bind key selection to the expected issuer; never let issuer A's token verify against key B out of policy.
3. Enforce `aud` per API; never "trust the issuer" and skip audience.
4. When a principal belongs to multiple tenants, verify active membership in the target tenant.
5. Read resource `tenantId` from the database, never trusting paths/headers to grant permissions.
6. If the issuer list changes dynamically, implement approval/revocation workflows, cache invalidation, auditing, and monitoring.
7. Never fetch metadata from untrusted URLs, preventing SSRF and unsafe trust-on-first-use.

## 14. Opaque tokens: when there are no JWT claims to parse

An OAuth2 resource server may receive opaque access tokens. Do not attempt to split them into three parts and parse JWTs. Use a trusted Authorization Server's introspection endpoint, verifying `active=true` and audience/issuer/scope attributes per the AS/API contract.

~~~text
Opaque bearer token
     |
     v
Trusted introspection endpoint
     |
     v
active? issuer? audience? scope? expiration?
     |
     v
Map authorities + domain authorization
~~~

Opaque introspection can reflect token revocation faster when each request checks current status, at the cost of network/cache tradeoffs and AS limits. Never infer "`active=true` ⇒ this API grants full read access"; audience and resource permissions must still obey policy.

## 15. Common error table

| Symptom | Cause | Fix |
| --- | --- | --- |
| API trusts scopes from merely decoding a token | Parsed JWT without verifying | Use `JwtDecoder`/Resource Server filter |
| Accepts JWT signed by an unknown issuer | Read issuer from claim and trusted it blindly | Trusted issuers allow-list |
| API B token works on API A | Missing `aud` validation | Configure API A's expected audience |
| Staging issuer token works in production | Used `startsWith`/domain substring | Exact issuer matching and isolated environments |
| ID token accepted as access token | Missing `typ`/audience/profile checks | RFC 9068 `at+jwt` type validator |
| `alg=none` accepted | Flawed custom verifier | Algorithm allow-list, reject unsigned |
| `jku` header dictates key download | Loaded untrusted key URL | Trusted JWKS only |
| Expired token remains usable for too long | Excessive clock skew | Reduce skew; test clearly expired tokens |
| Future `nbf` token accepted | Missing timestamp validation | Use standard validators |
| Valid scope still returns 403 | Wrong `SCOPE_` mapping or authority typo | Check `JwtGrantedAuthoritiesConverter` and HTTP rules |
| Strong scope with wrong `aud` still gets 200 | Authorization ran before JWT validation | Gate via resource server decoder before claims |
| Custom decoder stops checking `exp`/`iss` | Replaced default validators with one validator | Combine all required validators |
| Self-created client token accepted | Signature not verified with trusted key | RSA/JWKS verifier; test forged keys |
| `mockJwt()` tests pass yet wrong-issuer tokens work | Mock bypasses decoder | Add real HTTP tests with signed tokens |
| Role in tenant A grants access in tenant B | Trusted `roles` claim alone | Membership + tenant resource predicate |
| `client_id` mistaken for audience | Conflated OAuth client and Resource Server | Set `aud` per API resource indicator |
| JWT has unknown `kid` | Verifier fetched untrusted key | Select keys from configured JWKS; fail closed |
| Resource server holds signing private key | Mixed AS and RS responsibilities | AS holds private key; RS holds public only |
| API breaks when IdP/JWKS is down | Unplanned key discovery/caching | Bounded timeout/retry/cache; never skip verification |
| Raw JWT exposed in logs | Logged Authorization header | Redact tokens/sensitive claims; log reason codes |

## 16. Pre-production checklist

1. Does the API accept only **access tokens** matching the agreed profile?
2. Does the JWT undergo cryptographic signature verification with trusted keys/algorithms?
3. Are `alg=none` and non-allow-listed algorithms rejected?
4. Are `kid`/`jku` prevented from pointing key retrieval to untrusted locations?
5. Is `iss` exact and restricted to allowed issuers/environments?
6. Does `aud` contain the exact API identifier rather than a client ID?
7. Are `exp`/`nbf` and clock skew enforced with negative tests?
8. If using RFC 9068, is `typ=at+jwt`/`application/at+jwt` verified?
9. Are required claims `sub`/`client_id`/`iat`/`jti` per profile fully checked?
10. Does a custom `JwtDecoder` retain all necessary issuer/time/type/audience validators?
11. Does Spring `scope`/`scp` mapping to `SCOPE_` match the IdP contract?
12. Are custom roles mapped only **after** token validation?
13. Do HTTP rules separate GET vs. POST without letting READ scope perform WRITE?
14. After scope checks, does business logic still check tenant/owner/resource/entitlement?
15. Is the multi-issuer trust list protected from client manipulation?
16. Are there real tests for valid signed tokens and invalid signature/iss/aud/typ/exp/scope?
17. Is `mockJwt()` used solely for authorization rule tests, never confused with signature tests?
18. Are private signing keys kept out of production resource servers?
19. Do JWKS rotation, caching, and issuer outages fail closed clearly?
20. Are `invalid_token`/`insufficient_scope` events monitored without logging raw tokens?
21. If the API uses cookies/browser credentials, was CSRF evaluated instead of disabled "because JWT"?
22. Are regression tests run when upgrading Spring Boot/Security/OAuth2 providers?

## 17. Practice exercises

**Exercise 1 – Cross-API token.** Issue a token with `scope=ledger.read` but `aud=["urn:reports-api"]`. Verify Ledger API returns 401. Explain why the valid scope is never evaluated.

**Exercise 2 – Exact issuer.** Change `iss` from `tenant-a` to `tenant-b` while keeping the test RSA signature. Verify 401; never "fix" it with `startsWith`.

**Exercise 3 – ID token confusion.** Change header `typ` from `at+jwt` to `JWT` in a validly signed token. Verify the RFC 9068 validator rejects it. Discuss differences between ID tokens and access tokens.

**Exercise 4 – Signature forgery.** Sign the same claims with another keypair and verify 401. Why are a valid-looking payload and scopes meaningless?

**Exercise 5 – Scope mapping.** Issue a token with `scope=ledger.read` and call POST; verify 403. Switch to `ledger.write` and verify 200. Explain the `SCOPE_` prefix.

**Exercise 6 – Multi-valued audience.** Put both `reports-api` and `ledger-api` in `aud`; verify the "contains expected audience" policy. If single-audience-only is desired, design an extra validator and test it.

**Exercise 7 – Timestamps.** Create a token expired by several minutes, a token with future `nbf`, and a token missing `exp`. Ensure the appropriate validators reject them.

**Exercise 8 – Custom roles.** Add IdP claim `roles=["TENANT_EDITOR"]`. Build an allow-listed role converter; test that roles are not mapped from unverified JWTs and tenant A cannot edit tenant B's resources.

**Exercise 9 – Trusted multi-issuer.** Configure two allow-listed issuers and reject a third. Ensure each issuer uses its own keys and audience policy.

**Exercise 10 – JWT vs. opaque.** Compare local JWT validation with opaque introspection when a role is revoked. Describe cache/latency/consistency contracts and fail-closed behavior.

**Exercise 11 – Security test quality.** Write two separate layers: one using `mockJwt()` to test endpoint permissions, and one using real signed JWTs to test signature/issuer/audience/type/timestamps; explain what each layer proves.

**Completion criteria:** accurately explain issuer/audience semantics; block cross-API or unknown-issuer tokens regardless of scopes; verify signature/key/algorithm/type/timestamps before using claims; configure Spring Resource Server and validators properly; distinguish 401 vs. 403; test with real signed tokens; and add object-level authorization where needed.

## 18. Official references

- RFC 9068 – **JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens**, issuer/audience/type/signature/time requirements: https://www.rfc-editor.org/rfc/rfc9068.html
- RFC 7519 – **JSON Web Token (JWT)**, `iss`, `aud`, `exp`, `nbf`, `iat`: https://www.rfc-editor.org/rfc/rfc7519.html
- RFC 8725 – **JSON Web Token Best Current Practices**, algorithms/token substitution: https://www.rfc-editor.org/rfc/rfc8725.html
- RFC 8707 – **Resource Indicators for OAuth 2.0**: https://www.rfc-editor.org/rfc/rfc8707.html
- Spring Security 6.5 – **OAuth2 Resource Server JWT**, RFC 9068 validation, `JwtDecoder`, and custom audiences: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 – **JwtValidators.AtJwtBuilder API**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.AtJwtBuilder.html
- Spring Security – **Resource Server Multi-tenancy** and trusted issuer resolver: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- Spring Boot – **OAuth2 Resource Server Configuration**, `audiences` property: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- Spring Security – **Opaque Token Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security – **Testing OAuth2 Resource Server**, `mockJwt`: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
