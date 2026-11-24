# Distinguishing API Keys, Opaque Tokens, and JWTs Before Choosing an Integration Approach

When building an API with **Spring Security Servlet**, three options are often placed side by side: **API keys, opaque tokens, and JWTs**. Yet these are not three "login algorithms" of the same nature. An API key mainly describes a **credential issued to a client/integration**; an opaque token describes **how the resource must verify the token's value**; and JWT describes a **token data format and its claims**. An OAuth2 access token can be either opaque or a JWT, and an API key is often also an unstructured secret string. Therefore, you must decide on **subject, trust source, issuance lifecycle, verification, and revocation** before choosing an integration library.

This lesson belongs to the **Custom Authentication** section of the **Spring Security – Servlet** module. Examples use Spring Security 6.x, Java 17, and Spring Boot 3.3.5, clearly distinguishing **runnable examples** (API key with MockMvc) from **integration templates dependent on an authorization server** (OAuth2 opaque/JWT).

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain API keys, opaque tokens, and signed JWTs without confusing **format** with **token issuance purpose**.
2. Distinguish `authentication`, `authorization`, `scope`, `principal`, `issuer`, and `audience`.
3. Choose between **key store** lookup, **introspection**, and **JWT signature/claim validation** for each use case.
4. Evaluate latency, caching, revocation, dynamic permissions, replay risk, key rotation, and potentially exposed data.
5. Use Spring Security Servlet in the right role: custom API-key filter/provider or built-in OAuth2 Resource Server.
6. Write tests for missing/invalid credentials, insufficient scopes, wrong-target tokens, revoked tokens, and tenant boundaries.
7. Recognize when **not to write your own JWT parser, bearer-token filter, or OAuth2 protocol**.

## 2. Three Conceptual Axes to Keep Separate

### 2.1. What Is the Credential Used For?

A credential is evidence presented by the caller to the API. It can represent a user, service account, integration, project, device, or a user's authorization delegated to a client.

**API keys** are usually issued by the API owner to an integration/service. A key can carry fixed access permissions, expiration, quotas, and tenant bindings. An API key does not by itself imply it represents a browser-logged-in user.

**Access tokens** are typically issued under an authentication and authorization protocol/policy, such as OAuth2. They can represent a client via the client credentials flow or user-delegated access via the authorization code flow. Opaque and JWT are merely two ways to represent/verify tokens.

OpenID Connect **ID tokens** are typically JWTs, yet exist to convey authentication info to a client. APIs **must never accept an ID token as an access token** merely because it shares an issuer or valid signature.

### 2.2. What Shape Does the Token Have?

~~~text
X-API-Key: random-secret-issued-to-service-42
Authorization: Bearer opaque-random-access-token
Authorization: Bearer eyJ...encoded-header.eyJ...encoded-payload.signature
~~~

All three values are purely illustrative. The `Authorization: Bearer` header **does not prove** a token is a JWT; an OAuth2 resource server can receive an opaque token or a signed JWT in that same header depending on configuration. An API key can also be placed in an Authorization header under a system-defined protocol.

Compact JWS-formatted JWTs typically have three parts `header.payload.signature`, with base64url-encoded header/payload. **Base64url is not encryption**: a JWS payload can normally be read by anyone holding the token. JWE supports encryption, which is a different mechanism.

### 2.3. Who Has Authority to Decide a Credential Is Valid?

- **API key**: a key store/verifier trusted by the API system, capable of looking up the key ID and comparing hashes.
- **Opaque token**: an authorization server/introspection endpoint or trusted token store supplying active state and permissions.
- **JWT**: the resource server using trusted keys to verify the signature, then checking `iss`, `aud`, expiration, token type, scopes, and related claims/constraints.

**Merely extracting a name/role string from a request does not mean authentication succeeded.** A trusted Authentication must emerge *after* verification, never immediately upon parsing a header or decoding JSON.

## 3. Overall Comparison Table

| Criterion | API Key | Opaque Access Token | JWS-Format JWT Access Token |
| --- | --- | --- | --- |
| Concept | Credential typically issued to client/integration | Access token requiring lookup/introspection to obtain trusted contents | Token format carrying claims, typically signed |
| Shape | Usually a random string, no universal standard | Opaque value, not self-describing at the resource server | JWS: header.payload.signature |
| Common subject | Client, service, integration | User or client depending on OAuth2 grant | User or client depending on OAuth2 grant |
| Verification | Key store, hash, status, scopes | Token store or introspection | Signature and claim validators |
| Must call issuer per request? | Depends on key-store/cache | Usually yes with online introspection; cacheable | Usually no, once trusted JWKS is cached |
| Revocation | Easy if checking live key status | Easier when introspecting live status | Harder when fully offline; needs TTL/denylist/state |
| Can permissions go stale? | Yes if key metadata is cached | Yes if introspection is cached | Yes until expiry or with additional checks |
| Data exposed inside token | Usually no claims, yet the key itself is a secret | Exposes no claims directly, yet bearer token is a secret | JWS payload is readable; omit unnecessary secrets/PII |
| Spring Security integration | Custom filter/provider common | `oauth2ResourceServer().opaqueToken(...)` | `oauth2ResourceServer().jwt(...)` |
| Example use case | Partner backend syncing data | OAuth2 needing centralized permissions/revocation | Many microservices needing local signature verification |
| Risk if stolen | Replayable | Replayable | Replayable |

**Note:** rows reflect typical designs, not a universal contract for every provider. API keys can also be short-lived; JWTs can also be introspected; opaque tokens can also use a local token database. **Bearer tokens** are usable by whoever possesses the value unless the system adds sender-constraining mechanisms such as mTLS-bound tokens or DPoP.

## 4. API Keys: Simple for Clients, Yet Lifecycle Must Be Serious

API keys fit when you own an API and a set of backend clients must call it automatically **without acting on behalf of a specific user**. A client is issued a secret, sends it in an agreed header, and the API verifies the key before granting resource access.

### 4.1. Proper Key Design

A trustworthy system typically must:

- Generate keys with a **CSPRNG** and high entropy; never use emails, usernames, timestamps, or predictable data as secrets.
- Include a **non-secret key ID/prefix** for fast lookup while still requiring a valid secret.
- Display the raw key **once** upon creation; store an appropriate hash/digest rather than a reusable value.
- Bind the key to `clientId`, owner, tenant, scopes, status, issue/expiry dates, and quotas.
- Support key rotation with an approved overlap window, then revoke the old key.
- Enforce HTTPS, rate limiting, auditing, secret scanning, and never log raw keys.
- Separate production, staging, and development keys; never share one key across all integrations.

Illustrative record shape:

~~~text
key_id:        integration_102
key_hash:      SHA256(high-entropy secret)  [illustrative only]
client_id:     invoice-sync
tenant_id:     tenant-a
scopes:        [invoice.read]
status:        active
expires_at:    2027-06-01T00:00:00Z
last_used_at:  non-sensitive metadata
~~~

Because API keys require high entropy, storing a **SHA-256 digest** can be reasonable for long random keys; this is **completely different from hashing user passwords**. User-chosen passwords typically have low entropy and need bcrypt/Argon2id/PBKDF2/SCrypt with an appropriate work factor. For low-entropy keys, fast digests remain easy to brute-force.

### 4.2. Where Clients Store Keys

- Server-to-server backends can store keys in a secret manager or protected environment.
- Never hardcode **secret API keys** in browser-executed JavaScript or public mobile apps, where users can extract them.
- Never pass keys in URL query parameters: tokens easily leak into logs, history, monitoring, or referers.
- Avoid keys shared by thousands of frontend users in place of user authentication; one leaked key compromises everyone.

### 4.3. API Key Permissions

A valid key does not grant access to every endpoint. A key carrying only `invoice.read` must not POST invoice edits, access other tenants, or call admin endpoints. Scopes/authorities must come from the **verified server-side key record**, never from client-supplied headers like `X-Role: ADMIN`.

### 4.4. Limitations of API Keys

If you need user consent, delegated authorization for third-party apps, per-user session tokens, standard scopes/refresh/PKCE, or already have an authorization server, homegrown API keys can turn into a non-standard OAuth2 protocol. Consider proper OAuth2/OIDC, mTLS/workload identity, or other standard mechanisms before investing in custom builds.

## 5. Opaque Tokens: Trusting the Issuer/Token Store via Introspection

An opaque token is one whose contents the consumer **should not decode itself to grant permissions**. In OAuth2, an authorization server issues an access token and the resource server queries an **introspection endpoint** to receive active status, subject, client id, scopes, and metadata, per issuer capabilities.

~~~text
Client -> GET /api/invoices
          Authorization: Bearer opaque-access-token
        |
        v
Resource server / BearerTokenAuthenticationFilter
        |
        v
OpaqueTokenIntrospector
        |
        +-- HTTPS -> Authorization server introspection endpoint
        |            resource server authenticates with its own credentials
        |
        +-- response active, scopes, claims, metadata
        |
        v
Trusted Authentication + GrantedAuthority
        |
        v
Authorization -> controller (200) or reject (401/403)
~~~

If introspection reports inactive, the token must be rejected. If the endpoint times out or cannot confirm the token, **never fail open by default**. Implement explicit error handling, monitoring/timeouts/circuit breakers aligned with a fail-closed policy.

### 5.1. Advantages

- Centralized token-state authority: the issuer can revoke or reflect policy changes.
- The resource server does not verify JWS/JWKS when relying solely on opaque tokens via introspection.
- The token string need not carry readable claims; helpful for data minimization, though the bearer token itself remains a secret.
- Useful when an authorization server already provides reliable token introspection and dynamic permission control is high-priority.

### 5.2. Trade-Offs

- Network calls to introspection add latency, throughput overhead, and availability dependence on the AS.
- Introspection client ID/secret must be stored securely, distinct from user access tokens.
- Caching introspection lowers load yet delays revocation. With a 5-minute cache TTL, a revoked token can still be accepted by the resource server within the cache window per policy.
- Must verify audience, resource, and issuer/tenant/client bindings if required; `active=true` **does not mean every API is authorized**.
- Must handle malformed tokens, timeouts, HTTP errors, scope mapping, and never log raw tokens.

**Never claim "opaque always revokes immediately" if the app caches introspection results for long periods.** Actual revocation latency is an operational decision, not merely a format name.

## 6. JWTs: Self-Contained Claims with Signature and Constraint Checks

JWS-formatted JWTs typically carry a signature and JSON claims:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Illustrative payload (unsigned, so **not a valid token**):

~~~json
{
  "iss": "https://issuer.example",
  "sub": "user-123",
  "aud": ["invoice-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "invoice.read"
}
~~~

Common claims:

| Claim | Role | Watch Out For |
| --- | --- | --- |
| `iss` | Token issuer | Trust only configured/authorized issuers |
| `sub` | Represented subject | Do not infer full permissions from it alone |
| `aud` | Intended token audience | Tokens intended for other APIs must be rejected |
| `exp` | Expiration | Must verify strictly, with reasonable clock skew |
| `nbf` | Not valid before | Must verify if present |
| `iat` | Issued at | Useful for token-age policies/diagnostics |
| `scope` / `scp` | Scopes per issuer convention | Map accurately to authorities |
| `jti` | Token ID when issued by issuer | Usable for denylists/auditing if needed |

JWTs are not always OAuth2 access tokens: **ID tokens** and JWTs for other purposes must be distinguished. Resource servers must not accept client-login tokens as access tokens merely because the signature verifies.

### 6.1. JWT Validation Checklist

1. Verify JWS signature using trusted keys published by/configured for the issuer.
2. Allow only policy-approved JWS algorithms; never let a token's self-declared `alg` dictate crypto verification.
3. Verify `iss`, `aud`, `exp`, `nbf`, and max token age if needed.
4. Check token type/purpose to prevent **token confusion**.
5. Map scopes/roles per verified issuer; never read them prior to verification to grant permissions.
6. Check tenant/resource ownership and dynamic permissions at authorization time.
7. Manage JWKS/key ID `kid`, caching, and rotation from a configured trust anchor; never follow URIs suggested by an unverified token.
8. Use TLS, log redaction, and keep unnecessary secrets/PII out of JWT payloads.

**Decoding a payload with base64url only tells you what the token claims; it does not prove it is true.** In Spring Security, use `JwtDecoder`/OAuth2 Resource Server instead of hand-rolling signature parsing.

### 6.2. Advantages

- Resource servers can verify tokens locally, reducing per-request calls to the issuer.
- Many microservices can share trusted issuers and JWKS while enforcing separate audiences/scopes.
- Asymmetric signing means resource servers need only public keys to verify, not private signing keys.
- Verified claims can populate `Authentication` without looking up basic identity info on every request.

### 6.3. Drawbacks and Operational Duties

- **Revocation** is harder when resource servers are strictly offline and the token has not expired; consider short TTLs, denylists, dynamic policy checks, or introspection when needed.
- Embedded roles/scopes can go stale when a user is locked or permissions change.
- JWS payloads are **readable**; never embed passwords, secrets, or unnecessary personal data in tokens.
- Tokens can grow large; `Authorization` headers hit proxy/gateway size limits.
- JWKS caching, key rotation, network outages, algorithms, and issuer metadata must be managed explicitly.
- Sharing an HMAC secret across many resource servers widens secret-exposure blast radius; asymmetric signing usually separates issuance from verification more cleanly.

**JWT does not mean completely stateless.** Authentication may verify offline, yet dynamic authorization still needs policy/database/cache state; tokens may still require denylist or live account status checks.

## 7. Process for Choosing a Solution by Need

| Practical Need | First Direction to Evaluate | Conditions to Verify |
| --- | --- | --- |
| Partner backend calling a few APIs, no user delegation | Per-integration API key | Key entropy, scopes, expiry, rotation, quota, tenant |
| OAuth2 needing fast revocation and frequently changing permissions | Opaque introspection | Latency, AS availability, cache TTL, fail-closed |
| Many resource servers, high throughput, local validation needed | Signed JWT access token | Audience, issuer/JWKS, TTL, revocation/claim staleness |
| Need user consent / third-party login | Standard OAuth2/OIDC | Distinct access/ID tokens, grant and client types |
| Public browser frontend unable to protect a client secret | Authorization Code + PKCE or BFF by design | Token storage, session, XSS/CSRF, refresh handling |
| Service-to-service client credentials | OAuth2 client credentials or workload identity | Client identity, scopes, key rotation |
| Need per-tenant permissions with immediate changes | Any token type plus live state checks | Never trust client-sent tenant headers |
| Infrastructure lacks an AS and needs a small controlled integration | Simple API key | Prevent keys from becoming unlimited/non-revocable access |

### Decision Tree

~~~text
User delegation, consent, or standard OAuth2 issuer?
    |
    +-- YES --> Use OAuth2 access token
    |          |
    |          +-- Need near-real-time revocation/permissions updates?
    |          |       +-- Consider opaque introspection or JWT + state checks
    |          |
    |          +-- Need local verification across many resource servers?
    |                  +-- Consider signed JWT + audience/issuer/scope validators
    |
    +-- NO  --> Backend integration with few clients?
                 |
                 +-- Yes --> Per-client API key with expiry, scopes, and rotation
                 |
                 +-- No  --> Evaluate OAuth2 client credentials / mTLS
                                or trusted workload identity

Regardless of branch: verify identity + permissions + tenant boundary + revocation.
~~~

There is no rule forcing **one single style across the whole company**. You can use API keys for integrations, OAuth2 tokens for user APIs, and workload identities internally. However, keep endpoint-group policies separated so one credential never becomes a **privilege-bypass shortcut**.

## 8. Spring Security Servlet: Where Are Tokens/Keys Processed?

On the Servlet stack, `FilterChainProxy` picks a `SecurityFilterChain` by request matcher. Filters handle authentication before controllers are invoked. Credential data must be verified before placing a trusted `Authentication` into `SecurityContext` for authorization to evaluate.

~~~text
HTTP request
    |
    v
FilterChainProxy selects SecurityFilterChain
    |
    +--- API key: custom verifier/filter/provider
    |           -> key store/status/scopes
    |           -> trusted Authentication
    |
    +--- Bearer opaque: BearerTokenAuthenticationFilter
    |                 -> OpaqueTokenIntrospector
    |                 -> trusted Authentication
    |
    +--- Bearer JWT: BearerTokenAuthenticationFilter
    |              -> JwtDecoder/validators
    |              -> trusted Authentication
    |
    v
Authorization: scope/role/tenant/resource ownership
    |
    +-- sufficient permission -> DispatcherServlet/controller
    +-- missing/invalid -> 401 or 403 per policy/entry point
~~~

Distinguish clearly:

- **Authentication**: "Is the credential valid and who does it represent?"
- **Authorization**: "Is the authenticated caller allowed to invoke this exact resource/action?"
- **Chain selection**: `securityMatcher(...)` limits which URLs/methods enter a chain.
- **Rule selection**: `requestMatchers(...)` inside `authorizeHttpRequests` selects permission rules within that chain.

A valid token with insufficient scope usually causes 403; a missing/invalid token on a Bearer API usually causes 401. In other applications, entry points and CSRF can affect status codes; never infer everything from a single status code and ignore filter ordering.

### 8.1. API Keys Usually Require Custom Integration

Spring Security has no universal API-key standard across all products akin to OAuth2 Resource Server. Reasonable choices:

- `OncePerRequestFilter` for a very simple integration with a clear verifier and control over when the filter runs.
- `AuthenticationFilter + AuthenticationConverter + AuthenticationManager/Provider` to separate parsing, verification, principal mapping, and failure handling; helpful for multiple key types/tenants.
- Gateway/workload identity when the trust boundary is strictly verified without blindly trusting client headers.

A custom filter must grant `Authentication` **only after** the server verifies the key; never turn self-declared `X-Role` or `X-Tenant` into authorities. Place the filter in the right security chain without double-registering it as a standalone servlet filter.

### 8.2. OAuth2 Opaque Tokens: Built-In Integration

**Standalone** configuration snippet (do not merge directly into the API-key demo classes below):

~~~java
@Bean
SecurityFilterChain opaqueSecurity(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/api/**").hasAuthority("SCOPE_invoice.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
~~~

Place this inside `@Configuration` with required imports, the `spring-boot-starter-oauth2-resource-server` dependency, an authorization server supporting introspection, and resource server credentials. Example properties:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://issuer.example/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=api-resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_WITH_SECURE_SECRET_SOURCE
~~~

The values above are **placeholders**, not live servers/credentials. Never commit real client secrets. Introspection returns metadata and scopes; Spring Security maps scopes to `SCOPE_...` by convention, yet you still must verify mappings and issuer/tenant/resource bindings. `active=true` is not enough to permit every API.

### 8.3. JWT Access Tokens: Resource Server and Validators

**Standalone variant** configuration snippet:

~~~java
@Bean
SecurityFilterChain jwtSecurity(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/api/**").hasAuthority("SCOPE_invoice.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Place in a Spring configuration class importing `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, `Customizer`, and `@Bean`; requires the OAuth2 Resource Server starter and a real issuer/trusted keys.

Example property:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://issuer.example/realms/demo
~~~

**Do not treat `issuer-uri` as automatically enforcing the right business audience in every version.** Configure `aud` validation for your API and token purpose/type per policy. Example `JwtDecoder` bean building issuer and audience validators (illustrative snippet only):

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://issuer.example/realms/demo";
    String jwks = "https://issuer.example/realms/demo/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> base =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = token ->
        token.getAudience().contains("invoice-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Wrong audience", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(base, audience));

    return decoder;
}
~~~

This snippet requires importing `Jwt`/`JwtDecoder`/`NimbusJwtDecoder`/`JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator`, and `OAuth2Error`. Use only a JWKS URL determined from a trusted issuer, and validate JWS algorithms, access token purpose, and tenant as required. **Never use example URIs in real systems.**

### 8.4. Multiple SecurityFilterChains

When an app uses API keys for `/integrations/**` and OAuth2 for `/user/**`, define chain beans with matching `@Order` and `securityMatcher`s. Include a fallback policy for URLs outside matchers. **The first chain matching a request is selected**; `anyRequest()` inside a chain covers only requests that entered that chain. Never rely on a token valid at endpoint A to implicitly permit endpoint B.

## 9. Runnable Java 17 Example: Custom API Key Filter

To make clear that **before verification there is only a self-claimed secret, and only after verification are authorities attached**, this section builds a small Spring Boot MVC application:

- `GET /public/ping`: public, returns 200.
- `GET /api/data`: missing or wrong API key returns 401; valid key returns 200.
- Scope `SCOPE_data.read` is **server-created after** comparing the API key's digest.
- The demo is stateless per request, issuing no login session or access token.
- The key in properties is solely for running locally, **not a production API key storage pattern**.

For opaque/JWT, section 8's code requires an authorization server or signing keys and extra tests; never pretend that merely swapping an HTTP header yields a real token.

### 9.1. Directory Structure

~~~text
api-key-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/apikey/
    │   │   ├── ApiKeyDemoApplication.java
    │   │   ├── ApiKeySecurityConfiguration.java
    │   │   ├── ApiKeyFilter.java
    │   │   └── ApiController.java
    │   └── resources/application.properties
    └── test/java/example/apikey/
        └── ApiKeyIntegrationTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'api-key-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

File `src/main/resources/application.properties`:

~~~properties
# For local lab only; do not use in production.
demo.api-key=local-demo-only-secret-not-for-real-use
~~~

The illustrative key does not represent random production-issued secrets. Real systems need CSPRNG, key IDs, hashed keys stored in a DB/key store, secret sources from a secret manager, and rotation.

### 9.2. Bootstrap Class

File `src/main/java/example/apikey/ApiKeyDemoApplication.java`:

~~~java
package example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

### 9.3. ApiKeyFilter

File `src/main/java/example/apikey/ApiKeyFilter.java`:

~~~java
package example.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-API-Key";
    private final byte[] expectedDigest;

    public ApiKeyFilter(String configuredKey) {
        this.expectedDigest = digest(configuredKey);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
            .substring(request.getContextPath().length());
        return !"/api/data".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        if (candidate == null || candidate.isBlank()) {
            // No key: authorization rules will deny.
            chain.doFilter(request, response);
            return;
        }

        if (candidate.length() > 256
                || !MessageDigest.isEqual(
                    digest(candidate), expectedDigest)) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        // Verified server-side: now assign identity and scope.
        var verified = new UsernamePasswordAuthenticationToken(
            "demo-client",
            null,
            List.of(new SimpleGrantedAuthority("SCOPE_data.read")));

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static byte[] digest(String value) {
        try {
            MessageDigest sha256 =
                MessageDigest.getInstance("SHA-256");
            return sha256.digest(
                value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

In the example, `MessageDigest.isEqual` compares digests; production must handle duplicate headers, verify key status/expiry/scopes, and redact logs. Protecting user passwords must **not** use this plain SHA-256 formula.

The three-argument `UsernamePasswordAuthenticationToken` creates an authenticated token; thus it must be instantiated **only after** verifying the key. Never use the three-argument constructor inside a converter reading raw client input to self-grant roles. `SecurityContextHolder` must be cleared per request; here the filter uses `finally`, while the framework also manages lifecycle in the filter chain.

### 9.4. Security Filter Chain Configuration

File `src/main/java/example/apikey/ApiKeySecurityConfiguration.java`:

~~~java
package example.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiKeySecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, Environment environment)
            throws Exception {

        ApiKeyFilter keyFilter = new ApiKeyFilter(
            environment.getRequiredProperty("demo.api-key"));

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/data")
                    .hasAuthority("SCOPE_data.read")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, error) ->
                    response.sendError(401)))
            .addFilterBefore(
                keyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}
~~~

Because only GET endpoints are used, the demo **does not need to disable CSRF**. When adding POST, evaluate how clients send credentials and whether auto-attached cookies/sessions create CSRF risk. Never disable CSRF globally by default just because something is named "API".

The filter is instantiated **inside the chain builder method**, not declared as a standalone `@Component` or `@Bean`: this prevents Spring Boot from auto-registering an extra Servlet Filter outside the Spring Security chain and causing double execution. If you need to inject a filter bean in a large project, control auto-registration.

### 9.5. Controller

File `src/main/java/example/apikey/ApiController.java`:

~~~java
package example.apikey;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/data")
    public String data() {
        return "secured-data";
    }
}
~~~

The controller does not check `X-API-Key` itself; verification and authorization must happen in the security chain.

### 9.6. MockMvc Integration Tests

File `src/test/java/example/apikey/ApiKeyIntegrationTests.java`:

~~~java
package example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void missingKeyIsDenied() throws Exception {
        mockMvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongKeyIsDenied() throws Exception {
        mockMvc.perform(get("/api/data")
                .header("X-API-Key", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void matchingKeyCanAccessData() throws Exception {
        mockMvc.perform(get("/api/data")
                .header("X-API-Key",
                    "local-demo-only-secret-not-for-real-use"))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-data"));
    }
}
~~~

The tests verify public/missing/invalid/valid API keys through Spring Security filters. Do not interpret them as proof that JWT signature validation or opaque introspection works. For OAuth2 variants, write dedicated tests with a real or controlled-mock decoder/introspector, issuer/audience/scope checks, and service failures.

### 9.7. Run Commands and Sample HTTP Calls

With Gradle and Java 17:

~~~bash
gradle test
gradle bootRun
~~~

If using the wrapper, run `./gradlew test` and `./gradlew bootRun` (Windows: `gradlew.bat`). The classes depend on Spring libraries, so bare `javac/java` without the classpath is insufficient.

Test on localhost when the server runs on the default port:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/data
curl -i -H 'X-API-Key: wrong' http://localhost:8080/api/data
curl -i -H 'X-API-Key: local-demo-only-secret-not-for-real-use' \
  http://localhost:8080/api/data
~~~

Results table per the demo configuration:

| Request | Status | Body on Success |
| --- | --- | --- |
| GET public without key | 200 | `pong` |
| GET private without key | 401 | Unspecified error body |
| GET private with wrong key | 401 | Unspecified error body |
| GET private with right key | 200 | `secured-data` |

Never use this sample key in real environments, and never share real keys in shell history/logs. Use non-TLS HTTP only for localhost demos.

## 10. How to Test OAuth2 Opaque/JWT Beyond the API Key Example

### 10.1. JWT Authorization Tests and Decoder Tests Are Two Different Levels

Spring Security Test provides the `jwt()` request post-processor to inject a mock `JwtAuthenticationToken` in MockMvc, useful for checking route/scope policies. **Code snippet** example (not a complete test class):

~~~java
mockMvc.perform(get("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_unrelated"))))
    .andExpect(status().isForbidden());
~~~

Requires the matching endpoint/chain and Spring Security Test/JUnit imports. **These two tests do not verify a real signature**: the `jwt()` mock helper supplies `Authentication` directly to the test. To test end-to-end security, you need tests using `JwtDecoder`, key/certificate fixtures, and tokens with bad signatures, expired timestamps, wrong issuers, wrong audiences, or wrong token purposes.

### 10.2. Opaque Introspection Tests

Key tests include:

- Non-existent or inactive token → request is rejected.
- Introspection active yet insufficient scope → 403.
- Introspection active and right scope → controller runs.
- Introspection endpoint times out or returns HTTP error → **never fail open**.
- Introspection returns mismatched tenant/client/subject → authorization denies.
- Introspection cache TTL and revocation window align with policy.

You can mock `OpaqueTokenIntrospector` for unit/integration tests checking mappings, while also performing contract/integration testing against a real authorization server or spec-compliant test double.

### 10.3. 401 vs 403

| Case | Typical Status | Meaning |
| --- | --- | --- |
| Missing bearer access token | 401 | No credentials for protected endpoint |
| JWT with bad signature, expired, or wrong audience | 401 | Authentication rejected |
| Inactive opaque token | 401 | Invalid token |
| Wrong API key | 401 (per demo) | Key verification failed |
| Valid credential yet insufficient scope | 403 | Insufficient authorization |
| Introspection endpoint network error | Per handling, never allow through | Infrastructure error, distinct from invalid token |
| POST rejected by CSRF | 403 possible | Not necessarily missing scope |

Entry points, bearer challenges, and filter chain configs can alter response details. Test both authentication and authorization, not just a single status.

## 11. Revocation, Caching, Key Rotation, and Dynamic Permissions

### 11.1. The Revocation Timing Question

Suppose an admin locks a client at **14:00**. Do you want the resource server to reject the very next request immediately, or accept a window of up to a few minutes?

- Stateful DB-backed API keys can be disabled the moment the verifier reads fresh state. If keys are cached, define invalidation or an explicit TTL.
- Uncached opaque introspection can reflect issuer state on the next request, trading off availability/latency.
- Offline-verified signed JWTs can remain valid until `exp`. If rapid revocation is required, add denylists, introspection, short TTLs, or live policy state checks.

**Revocation is a property of your verification and caching mechanism**, not magic coming from the label "opaque" or "JWT".

### 11.2. Rotation

- API key: issue a new key, allow new/old concurrently for a short window if justified, notify clients to switch, and disable the old key.
- Opaque token: the token issuer manages signing/opaque token stores and rotation/expiry separately; resource servers must update introspection credentials when rotated.
- JWT: the issuer rotates signing keys; resource servers refresh JWKS caches per policy while still accepting unexpired tokens signed with the prior key during a valid transition window.

Never deploy a rotation that wipes all old verifiers/keys before accounting for live tokens or a rollback path.

### 11.3. Stale Claims and Scopes

A user loses admin privileges after a JWT was issued. If the resource server reads authorities solely from the signed token, those privileges can persist until the token expires. If the business cannot tolerate that window, verify permissions dynamically or shorten token lifetimes. The same applies to API key metadata and opaque introspection **when cached**.

## 12. Multi-Tenancy, Browsers, and Runtime Environments

### 12.1. Tenant Boundaries

An API key with `tenant_id=A`, a JWT claiming `tenant=A`, or introspection returning tenant A must never authorize a request to `/tenants/B/orders`. The token may be valid, yet **resource ownership/tenant authorization** must deny it. Never trust an `X-Tenant: B` header as proof of access to B.

### 12.2. Tokens in Cookies and CSRF

CSRF involves **ambient credentials** automatically sent by browsers, classically session cookies. If a JWT lives inside an auto-sent cookie, "JWT is stateless" does **not** eliminate CSRF risk. Conversely, bearer tokens sent explicitly via `Authorization` headers by client code have a different threat model. Evaluate CSRF, `SameSite`, CORS, XSS, and token storage according to the actual client.

### 12.3. Logging, Monitoring, and Incidents

Never log raw API keys, `Authorization` headers, full tokens, introspection client secrets, signing private keys, or sensitive JWT claims. You may log key IDs, verified client IDs, request correlation IDs, auth mechanisms, error categories, routes, and statuses under a proper privacy policy. Maintain an incident response plan: identify compromised credentials, revoke keys/tokens, rotate signing keys when needed, and measure blast radius.

### 12.4. Rate Limiting

A stolen long-lived API key can be abused at very high request rates. The same holds for leaked JWT/opaque bearer tokens. Rate limiting should consider client ID, tenant, scope, IP, and route; never use quotas in place of credential verification. With introspection, monitor request volume and timeouts to avoid overloading the authorization server.

## 13. Mistakes to Avoid

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| API keys are always "less secure" than JWTs | Security depends on lifecycle/entropy/scopes/verification | Compare threat models and credential governance |
| Decodable JWT means trustworthy | Unverified payloads can be forged | Verify signature/claims before creating Authentication |
| Validly signed JWT works for every API | `aud`/purpose may differ | Check audience, type, and issuer |
| Using ID tokens to call resource APIs | Token confusion | Use access tokens issued for that API |
| Opaque `active=true` means full access | Authorization still needs scope/resource/tenant | Check full permissions after introspection |
| Introspection times out, so let it pass | Fail-open | Reject and handle infrastructure failure |
| Caching token state indefinitely | Revocation never takes effect | Approved TTL/invalidation |
| Storing keys in plaintext | DB leak exposes usable keys | Hash high-entropy keys; use key ID/rotation |
| Client sends `X-Role: ADMIN` to grant privileges | Untrusted authority | Scopes from verified server/issuer |
| Embedding API keys in frontend bundles | Users can extract the secret | Appropriate OAuth2 public client flow / BFF |
| Putting passwords/PII in JWT payloads | JWS payloads are readable | Minimal claims; encrypt when needed |
| Sharing one HMAC secret across all resource servers | Shared signing secret widens blast radius | Evaluate asymmetric keys/JWKS |
| Hand-coding JWT parsers/crypto | Easy to get algorithms/validators wrong | Spring Resource Server + `JwtDecoder` |
| Forgetting a fallback chain | Unmatched requests may lack security | Test matchers/chain coverage |
| Disabling CSRF just because "API/JWT" | Browsers may still auto-send cookies | Evaluate ambient credentials |
| Testing only with mocked `jwt()` | Does not prove signature verification | Test real decoder/introspection |

## 14. Self-Check Exercises

1. Can an API key be an opaque string? Why aren't API keys and opaque tokens "mutually exclusive formats"?
2. Is an OAuth2 bearer token in the `Authorization` header guaranteed to be a JWT?
3. A resource server only decodes a JWT and sees `ROLE_ADMIN` without verifying the signature. Why must it not let the request through?
4. A JWT has a valid signature and is unexpired, yet `aud` targets a different resource. What must the system do?
5. A service needs near-real-time access revocation while currently using 30-minute offline JWTs. State the trade-offs and solutions.
6. Opaque token introspection has a 10-minute cache. When a token is revoked, how does the cache window affect enforcement?
7. Design API keys for 10 partners: key ID, secret, scopes, tenant, rotation, quota, auditing, and monitoring.
8. Why can hashing high-entropy API keys use SHA-256 while user passwords should not use plain SHA-256?
9. In the example, why is the authenticated `UsernamePasswordAuthenticationToken` created only after verifying the key?
10. If a client sends a valid API key alongside `X-Tenant: B` while the key belongs only to tenant A, what must authorization do?
11. What does the `jwt()` MockMvc post-processor prove, and what does it not prove?
12. Explain the difference between `securityMatcher` and `authorizeHttpRequests.requestMatchers`.
13. If a JWT is stored in a cookie, can CSRF be disabled merely because "JWT is stateless"?
14. What risk arises when a resource server configures the right issuer yet forgets the audience validator?
15. When a JWT signing key rotates, how should live tokens and the JWKS cache be handled?
16. If the opaque introspection endpoint has downtime, may we "temporarily allow old tokens through"? What policy is required?
17. A user is locked yet roles inside their JWT have not expired; how can dynamic permissions be enforced?
18. Choose API key, opaque OAuth2 token, or signed JWT for three systems: ERP integration, many microservices, and an app delegating user data access. Give criteria, not just names.

## 15. Pre-Production Deployment Checklist

- [ ] Define real subjects (user, client, service, integration) and who is authorized to issue credentials.
- [ ] Mandate HTTPS; never pass secrets in URLs/queries or logs.
- [ ] High-entropy API keys, key IDs, hashed store, scopes, expiry, rotation, and revocation.
- [ ] Never embed secret API keys in public browser/mobile clients.
- [ ] Opaque tokens have introspection/token store, timeouts and fail-closed behavior, and cache TTL aligned with revocation.
- [ ] JWTs verify signature + algorithm + issuer + audience + lifetime + token purpose.
- [ ] Trust scopes/roles/tenant only from verified tokens/keys and enforce per-resource authorization.
- [ ] Have a strategy for dynamic permission updates and revoked tokens, with defined maximum staleness.
- [ ] Test JWKS/signing key rotation or introspection secret rotation.
- [ ] Never use ID tokens as access tokens; never roll your own crypto.
- [ ] Implement rate limiting, monitoring, auditing, and incident response.
- [ ] Never log raw tokens, `Authorization` headers, or secrets.
- [ ] Multiple `SecurityFilterChain` boundaries create no bypass paths.
- [ ] Evaluate cookies/CSRF/CORS/XSS based on how real clients transmit credentials.
- [ ] Include tests for 401/403, missing/invalid keys, wrong audience, expired/revoked tokens, and cross-tenant access.
- [ ] Prepare a migration/rollback plan if switching from API keys to OAuth2 or changing token formats.

## 16. Conclusion

**API keys** speak mainly to credentials issued for integrations and their dedicated lifecycle. **Opaque tokens** speak to verification backed by a stateful authority/introspection endpoint rather than self-reading tokens. **JWTs** speak to a claim-carrying format, typically signed for local resource-server verification; by themselves they do not solve revocation, dynamic permissions, or token-purpose validation.

Choose your model based on **who the principal is, who the issuer is, which source verifies the credential, how fast revocation must take effect, how many resource servers exist, and how scopes and tenants are controlled**. Once those questions are clear, Spring Security Servlet offers natural integration paths: custom API-key filters/providers for self-managed keys, `opaqueToken` introspection for opaque OAuth2 access tokens, or `jwt` resource server with `JwtDecoder`/claim validators for signed JWT access tokens.
