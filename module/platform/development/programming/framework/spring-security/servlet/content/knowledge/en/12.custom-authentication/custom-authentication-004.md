# Building an AuthenticationProvider and Validating Input Data

> **Topic:** Spring Security – Servlet stack, Java 17+, Spring Boot 3.x, and Spring Security 6.x. Learn how to write an `AuthenticationProvider` for a **custom authentication mechanism**, clearly separating *input format validation*, *verifying credentials from a trusted source*, *checking status/validity*, and *issuing an authenticated Authentication*. The main example uses an **API key consisting of an ID and secret** so learners see a flow different from username/password. The Spring snippets below require a Spring Boot project with dependencies; the standalone Java SE section can run directly on JDK 17.

## 1. Why Write an AuthenticationProvider?

Spring Security already ships built-in providers for common mechanisms, such as `DaoAuthenticationProvider` for username/password, providers for JWT, opaque tokens, etc. Do not rewrite a provider just to change how accounts are loaded: if you still use standard username/password, prefer `UserDetailsService` and `PasswordEncoder`.

A custom provider fits when the way evidence is presented/verified differs from built-in mechanisms, for instance:

- API keys issued by the application to API-calling services.
- One-time codes bound to a challenge and account, with expiration and replay protection.
- Devices or certificates with a custom verification workflow.
- An internal login ticket/attestation with a specialized format and verification mechanism.

The primary reason for creating a provider is to **encapsulate evidence-verification rules**, so servlet filters do not have to query databases directly or decide permissions.

### Flow Diagram

~~~text
HTTP request arrives at Servlet container
  |
  v
FilterChainProxy -> path-matching SecurityFilterChain
  |
  v
Authentication filter appropriate for the mechanism
  |  (reads header/body, checks initial size and structure)
  |  creates UNAUTHENTICATED Authentication
  v
AuthenticationManager (typically ProviderManager)
  |
  | selects AuthenticationProvider via supports(tokenType)
  v
Custom AuthenticationProvider.authenticate(requestToken)
  |
  | 1. check token type / input data
  | 2. locate credential record from trusted source
  | 3. check enabled, expiry, revocation, attempt policy...
  | 4. verify secret/signature/hash with appropriate algorithm
  | 5. obtain server-side identity and GrantedAuthority
  v
AUTHENTICATED Authentication or AuthenticationException
  |
  v
Filter places Authentication into the request's SecurityContext
  |
  v
AuthorizationFilter / Controller / response
~~~

**Authentication (authn)** answers "is this evidence valid, and who is this?". **Authorization (authz)** answers "is that identity allowed to perform this action?". Never let the client choose `GrantedAuthority` and copy it straight into the authenticated result.

## 2. AuthenticationProvider Contract: supports and authenticate

The core interface has two methods:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

This is a **condensed API signature** for explanation, not a redefinition of the interface in your project. `Authentication`, `AuthenticationException`, and `AuthenticationProvider` are Spring Security types.

### `supports(Class<?>)`

- Tells `ProviderManager` which *type* of authentication request the provider **can handle**.
- Does not check passwords/secrets, does not access databases, and does not decide authentication success.
- For a custom token, use `MyToken.class.isAssignableFrom(authentication)` if valid subclasses need support. For other tokens, return `false`.
- Returning true **does not guarantee** the provider will verify a specific credential. `authenticate(...)` must still verify all evidence.

### `authenticate(Authentication)`

- Receives a token representing an **unauthenticated claim**.
- On success: returns a trusted `Authentication`, `isAuthenticated()==true`, principal and authorities sourced from the server, with sensitive credentials removed where possible.
- On failure: throws an appropriate `AuthenticationException`, usually `BadCredentialsException` for invalid evidence.
- A provider can return `null` to give another provider a chance to handle it; however, for a token owned by the provider whose credential is clearly rejected, **do not return null as if it succeeded**. Every application must understand multi-provider configuration, ordering, and how `ProviderManager` handles exceptions.
- Database connection failures, timeouts, and programming bugs must **never** silently turn into successful authentication or bypass the verifier.

With `ProviderManager`, provider selection is based on token type; when multiple providers exist, providers may be tried in order depending on results and exception types. One provider throwing `BadCredentialsException` does not guarantee no subsequent provider will be tried in all configurations. Therefore, **review the entire set of providers** to ensure no unexpectedly weak fallback path exists.

## 3. Distinguishing Input Data from Verified Evidence

In the API key example, the client sends:

~~~http
GET /api/read HTTP/1.1
Host: api.example.test
X-Api-Key: client01.abcdefghijklmnopqrstuvwxyz012345
~~~

The value above is **demo data**, predictable and **not to be used as a production API key**. Real API keys must be generated with a cryptographic random number generator (`SecureRandom`), with sufficient entropy (such as 32 random bytes for the secret portion), sent over TLS, and protected like passwords.

Structure chosen for the example:

~~~text
<key-id>.<secret>
    |
    +-- key-id: 8..32 chars [A-Za-z0-9_-]
    +-- secret: 32..128 chars [A-Za-z0-9_-]
~~~

Why split into two parts?

- `key-id` is a **lookup index**, not authentication proof; knowing the ID alone grants no permissions.
- `secret` is the actual secret; the system stores only a **digest of a strong random secret** or an appropriate HMAC, never plaintext secrets in the datastore.
- Length and character constraints reject malformed input early, reducing DB/query/hash costs and eliminating values with dangerous header characters.
- Hashing high-entropy tokens can use SHA-256 in this model; **do not generalize raw SHA-256 to human-chosen passwords**. Passwords should use password-hashing algorithms with a work factor such as BCrypt/Argon2id/PBKDF2 per policy.
- Valid format **does not prove** the secret is right: you must look up the key ID, compare digests in a timing-leak-resistant way, and check revocation/expiry.

### Validation Layers

| Layer | Example Checks | If Invalid |
| --- | --- | --- |
| HTTP boundary / filter | Exactly one header? Too long? Right endpoint? | Reject safely or pass down the chain if key is absent and endpoint has its own policy. |
| Format parser | Matches `id.secret`, character set/length, no whitespace/CRLF, no extra dots. | Do not query DB, do not create an authenticated token. |
| Credential store | Does ID have a record? Is the record enabled and unrevoked? | Reject without revealing whether the user/key exists. |
| Verifier | Does the secret's digest match the trusted record? | `BadCredentialsException`; grant no authorities. |
| Provider result | Are principal and authorities sourced from the server and scoped to the credential? | Create authenticated result only when all conditions succeed. |
| Authorization | Does the endpoint require `SCOPE_READ` or another permission? | May return 403 even when authenticated. |

**Important:** Checks such as regex, `trim()`, `isBlank()`, length, or JSON parsing speak only to **format**. They cannot replace secret/signature verification and validity policies.

## 4. Designing a Custom Token: Only the Provider Creates Authenticated Results

Spring Security uses `Authentication` as the data carrier between filters, managers, and providers. For custom mechanisms, there is no need to force every request into `UsernamePasswordAuthenticationToken`: a dedicated token type makes `supports` clear and prevents other providers from mistakenly accepting the credential.

Create `src/main/java/com/example/customauth/ApiKeyAuthenticationToken.java`:

~~~java
package com.example.customauth;

import java.util.Collection;
import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthenticationToken(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        // Only factories inside this class call super to set true.
        super.setAuthenticated(verified);
    }

    public static ApiKeyAuthenticationToken forRequest(String rawApiKey) {
        return new ApiKeyAuthenticationToken(
                "unverified-api-key", rawApiKey, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String serviceName,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthenticationToken(
                serviceName, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use the verified factory inside a trusted provider");
        }
        super.setAuthenticated(false);
    }
}
~~~

**Design intent:**

- The `forRequest(...)` factory always creates an **unauthenticated** token with empty authorities. It trusts neither principal nor permissions from headers.
- The `verified(...)` factory is used by the provider **after verification**; the private constructor is a basic programming guardrail.
- Calling `setAuthenticated(true)` on an externally held instance is rejected. However, the `verified(...)` factory remains public in the illustrative code so the provider can call it: **it is not a security boundary against untrusted Java code in the same process**. Applications must control factory call sites through design/modules, code review, and testing. Never accept a client-supplied verified flag.
- `getCredentials()` on the input token holds the raw key only within the scope needed for processing; the output token uses `null`. Never log/tokenize objects holding secrets; Java Strings cannot immediately erase bytes from the heap.
- The resulting `Authentication` object is **not an HTTP session**. For stateless APIs, it exists only in the current request's context.

If the system uses OTPs or signatures instead of API keys, you can swap the verifier and credential type, while keeping the principle: unauthenticated input token → provider verifies → authenticated result token.

## 5. Reusable Input Parser: `ApiKeyFormat.java`

Create the file:

~~~java
package com.example.customauth;

import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ApiKeyFormat {

    private static final Pattern KEY_SHAPE = Pattern.compile(
            "([A-Za-z0-9_-]{8,32})\\.([A-Za-z0-9_-]{32,128})"
    );

    private ApiKeyFormat() {}

    public record Parts(String keyId, String secret) {}

    public static Optional<Parts> parse(String raw) {
        // 32 ID chars + 1 dot + 128 secret chars.
        if (raw == null || raw.length() > 161) {
            return Optional.empty();
        }

        Matcher match = KEY_SHAPE.matcher(raw);
        if (!match.matches()) {
            return Optional.empty();
        }

        return Optional.of(new Parts(match.group(1), match.group(2)));
    }
}
~~~

This is a **format checker**, not an authentication verifier. Several explicit decisions:

1. `Matcher.matches()` requires the **entire string** to match the regex, disallowing extra leading/trailing characters.
2. Never call `trim()` and accept malformed data; HTTP headers containing whitespace/CRLF must be rejected rather than "fixed up" into another key.
3. `raw.length()` bounds size before regex grouping runs, reducing processing cost on abnormal inputs.
4. `[A-Za-z0-9_-]` is a small ASCII set; for instance, it disallows Unicode lookalikes or extra dots.
5. A key with valid shape whose secret lacks entropy still **fails real key-issuance requirements**. The validator must accompany key generation from `SecureRandom`.

Keep the validator on the server and reuse it when creating demo fixtures/tests. If the format ever needs to change, version/constrain it so old-protocol secrets are not inadvertently accepted outside policy.

## 6. Credential Store: Store Only Hashes/Digests and Trusted Metadata

Create `ApiKeyRecord.java`:

~~~java
package com.example.customauth;

import java.time.Instant;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;

public record ApiKeyRecord(
        String id,
        String subject,
        byte[] secretDigest,
        boolean enabled,
        Instant expiresAt,
        List<GrantedAuthority> authorities) {

    public ApiKeyRecord {
        // Copy so nothing external can mutate digest/authorities directly.
        secretDigest = secretDigest.clone();
        authorities = List.copyOf(authorities);
    }

    @Override
    public byte[] secretDigest() {
        return secretDigest.clone();
    }
}
~~~

Create `ApiKeyStore.java`:

~~~java
package com.example.customauth;

import java.util.Optional;

public interface ApiKeyStore {
    Optional<ApiKeyRecord> findById(String id);
}
~~~

The record holds: ID, service/subject name, digest of the secret, enabled status, expiration, and **server-granted** authorities. There is no method accepting permissions from the request.

In production, `ApiKeyStore` typically reads from a database with a unique ID and revocation policy, e.g., this **illustrative** SQL query:

~~~sql
SELECT key_id, subject_id, secret_digest, enabled, expires_at
FROM service_api_keys
WHERE key_id = ?;
~~~

The `?` is a bind parameter; never concatenate client strings into SQL. Authorities can be loaded from a scope table associated with the key. Never store raw keys and never expose digests via APIs. Key update/revocation transactions must have auditing and explicit admin authorization.

### Digest Function for High-Entropy Secrets

Create `ApiKeyDigests.java`:

~~~java
package com.example.customauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class ApiKeyDigests {

    private ApiKeyDigests() {}

    public static byte[] sha256(String secret) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return digest.digest(
                    secret.getBytes(StandardCharsets.US_ASCII));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is not available", ex);
        }
    }
}
~~~

**Proper scope:** the `secret` part of an API key is **strongly randomly generated**, not a user-chosen password. SHA-256 of a 256-bit random secret does not carry the same dictionary-attack risk as SHA-256 of a weak password. Even so, you can use HMAC with a server-side pepper/key for extra protection depending on the threat model; manage and rotate the pepper separately. Do not turn this example into an account password store.

If storing digests in a DB as binary/hex, specify format, encoding, and indexing clearly. To compare two digests, use `MessageDigest.isEqual(a, b)` instead of `Arrays.equals(...)` on the secret verification path; even then, **the overall API is not automatically constant-time** because key ID existence, query duration, and other branches can still vary. Use rate limiting, monitoring, and appropriate mitigations.

## 7. Real Provider: Format → Lookup → Validity → Verify → Result

Create `ApiKeyAuthenticationProvider.java`:

~~~java
package com.example.customauth;

import java.security.MessageDigest;
import java.time.Instant;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

public final class ApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final ApiKeyStore store;

    public ApiKeyAuthenticationProvider(ApiKeyStore store) {
        this.store = store;
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return ApiKeyAuthenticationToken.class.isAssignableFrom(
                authenticationType);
    }

    @Override
    public Authentication authenticate(Authentication input) {
        if (!(input instanceof ApiKeyAuthenticationToken token)) {
            return null;
        }

        if (!(token.getCredentials() instanceof String raw)) {
            throw new BadCredentialsException("Invalid API key");
        }

        ApiKeyFormat.Parts parts = ApiKeyFormat.parse(raw)
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid API key"));

        ApiKeyRecord record = store.findById(parts.keyId())
                .orElseThrow(() ->
                    new BadCredentialsException("Invalid API key"));

        if (!record.enabled()
                || !Instant.now().isBefore(record.expiresAt())) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] presented = ApiKeyDigests.sha256(parts.secret());
        byte[] expected = record.secretDigest();

        if (!MessageDigest.isEqual(expected, presented)) {
            throw new BadCredentialsException("Invalid API key");
        }

        return ApiKeyAuthenticationToken.verified(
                record.subject(), record.authorities());
    }
}
~~~

### Step-by-Step Breakdown

**Step 1 — Type guard.** `supports` must match the token type. Checking `instanceof` inside `authenticate` is defense-in-depth when the provider is called directly. Never accept `UsernamePasswordAuthenticationToken` or JWT bearer tokens if that is not this provider's responsibility.

**Step 2 — Accept only the right credential type.** If the token does not hold a String raw key, fail; never arbitrarily call `toString()` on a client object and treat it as a secret.

**Step 3 — Bounded input parsing.** `ApiKeyFormat.parse` validates format before querying. Overly long tokens, unusual Unicode, multiple dots, whitespace, or control characters are rejected.

**Step 4 — Server-side lookup.** `keyId` is merely an index. Never read subject names/authorities from client-supplied bodies/headers. Non-existent key IDs and wrong keys use the same `Invalid API key` message; never disclose "this ID exists".

**Step 5 — Status check.** A disabled or expired key is invalid even if the secret matches. `Instant.now().isBefore(record.expiresAt())` makes the key **expire right at the expiry timestamp**. In real systems, also check revocation, tenant, allowed scopes, rotation, and clock-skew policy per protocol.

**Step 6 — Digest comparison.** Only the right secret receives a result. Digest comparison belongs in the provider, not in a servlet filter/controller.

**Step 7 — Build authenticated result.** `record.subject()` and `record.authorities()` come from the server source. The result does not retain the raw API key. If the app needs to distinguish service identities from end-user identities, the principal should have a distinct type and policies should account for it; do not assume a service API key equals a fully logged-in human user.

### Why Doesn't the Provider Call SecurityContextHolder?

The provider contract is **verify and return a result**. The servlet authentication filter/integration manager owns context management, request lifecycle, and HTTP responses. If a provider calls `SecurityContextHolder.setContext(...)` itself, it becomes coupled to HTTP and risks leaking state across requests/threads or breaking other flows.

### Why Is There No `UsernameNotFoundException`?

This is API key authentication, not username/password via `UserDetailsService`. For API keys, throwing `BadCredentialsException` for invalid credentials is appropriate. For OTP/custom certificate tokens, the specific exception may differ; what matters is never issuing a new Authentication when verification fails.

## 8. Servlet Filter Reads Header, Calls Manager, Handles Errors Safely

Create `ApiKeyHeaderFilter.java`:

~~~java
package com.example.customauth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Enumeration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyHeaderFilter extends OncePerRequestFilter {

    private static final String HEADER_NAME = "X-Api-Key";
    private final AuthenticationManager manager;

    public ApiKeyHeaderFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders(HEADER_NAME);

        if (!values.hasMoreElements()) {
            // No evidence yet: delegate onward to authorization policy.
            chain.doFilter(request, response);
            return;
        }

        String raw = values.nextElement();

        if (values.hasMoreElements()) {
            // Duplicate headers may be combined differently by proxies/frameworks.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        final Authentication verified;
        try {
            verified = manager.authenticate(
                    ApiKeyAuthenticationToken.forRequest(raw));
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            // Do not echo secret, ID existence, or exception message.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            // Do not carry this request's principal to another thread/request.
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Why doesn't this filter compare hashes itself?** Because the filter only reads the header and delegates to `AuthenticationManager`. That lets you unit test the provider independently and integration test the HTTP filter via MockMvc.

**Why catch exceptions only around `manager.authenticate`?** Wrapping the entire `chain.doFilter(...)` as a login error could misdiagnose downstream controller or authorization failures, or even attempt to send `401` after the response has committed. The example catches only `AuthenticationException` raised during the authentication phase.

**Why pass through requests missing the header?** A public endpoint may not require a key. For protected endpoints, authorization will see no authenticated principal and deny per configuration. If the system requires a key on every path, you can reject directly in the filter, while explicitly defining policy for health endpoints.

**Why check duplicate headers?** Many proxies combine repeated headers into comma-separated strings or preserve multiple values. The policy here is a single key; even cases combined into a string failing the regex are rejected by the provider.

**Note on async processing:** `OncePerRequestFilter` has specific dispatch policies; `SecurityContextHolder` defaults to the current thread. In applications with async/error dispatches, check context propagation, cleanup, and filter dispatch rules properly; never assume setting context once suffices for all background tasks.

## 9. Spring Security 6 Configuration: Register the Filter Only Once

Create `SecurityConfig.java`:

~~~java
package com.example.customauth;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    ApiKeyAuthenticationProvider apiKeyProvider(ApiKeyStore store) {
        return new ApiKeyAuthenticationProvider(store);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            ApiKeyAuthenticationProvider provider) throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, problem) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/read").hasAuthority("SCOPE_READ")
                .anyRequest().denyAll())
            .addFilterBefore(
                new ApiKeyHeaderFilter(manager),
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Important explanations:**

1. `securityMatcher("/api/**")` selects the chain for the API group. `requestMatchers(...)` inside `authorizeHttpRequests` determines permissions **within the selected chain**. Do not confuse them.
2. `ApiKeyHeaderFilter` is instantiated with `new` inside the chain configuration, **not** annotated with `@Component` or exposed as a `@Bean`. If Boot auto-registers the same filter as a servlet-container filter, it can run outside `FilterChainProxy` or run twice. Direct instantiation avoids double registration in the example.
3. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` uses a filter ordering anchor known to Spring Security; it does not mean the demo enables form login. This is API-key authentication, not `POST /login`.
4. `ProviderManager(provider)` holds the custom provider for the filter; verification remains separated from the filter. If adding another provider, review token support and ordering so no weak fallback authenticates the same credentials.
5. `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository` demonstrate not persisting authenticated principals across requests. Subsequent requests must resend the key.
6. `csrf(AbstractHttpConfigurer::disable)` here applies only to a **stateless API receiving secrets via headers rather than credentials automatically attached by browser cookies**. Never copy disabling CSRF into cookie/session form-login web apps without a threat model assessment.
7. `exceptionHandling.authenticationEntryPoint(...)` returns `401` when a protected endpoint needs authentication and the request lacks a key. `403` can still occur when authenticated but missing `SCOPE_READ`.
8. The second chain denies all so endpoints outside `/api/**` are not left completely unguarded when the demo declares only one API chain. In real apps with UI/form login, replace the fallback with a dedicated policy chain.
9. API keys must be sent over HTTPS; if the app sits behind a proxy, the proxy must protect TLS and never log or forward secret headers to untrusted destinations.

### HTTP Status Does Not Map 1-to-1 to a Single Exception Type

- Missing key on `/api/read`: typically `401 Unauthorized` via the entry point.
- Wrong/expired/revoked key: `AuthenticationException` is converted by the filter into a generic `401`.
- Valid key lacking authority: authorization denies, typically `403 Forbidden`.
- Endpoint outside the API chain: fallback deny; exact status may vary by handler/entry point, but access is denied.
- Database error: must never convert into `200` or self-grant a principal; define `503`/`500` policy and appropriate metrics for operations.

## 10. Profile-Scoped Demo API Key Seed, Never Embedded Production Secrets

To make the examples runnable with Spring Boot, create an in-memory `ApiKeyStore` when the `demo` profile is active. Create `DemoKeyStoreConfig.java`:

~~~java
package com.example.customauth;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@Profile("demo")
public class DemoKeyStoreConfig {

    @Bean
    ApiKeyStore apiKeyStore(Environment environment) {
        String raw = environment.getRequiredProperty("DEMO_API_KEY");

        ApiKeyFormat.Parts parts = ApiKeyFormat.parse(raw)
            .orElseThrow(() ->
                new IllegalStateException("Invalid demo key format"));

        ApiKeyRecord record = new ApiKeyRecord(
                parts.keyId(),
                "svc-demo",
                ApiKeyDigests.sha256(parts.secret()),
                true,
                Instant.parse("2099-01-01T00:00:00Z"),
                List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        return id -> record.id().equals(id)
                ? Optional.of(record)
                : Optional.empty();
    }
}
~~~

The example uses a secret **externalized from code** via the `DEMO_API_KEY` environment variable. The following fixed value is **only for localhost testing and tests**, lacking sufficient secrecy for real use:

~~~text
client01.abcdefghijklmnopqrstuvwxyz012345
~~~

**In production**, replace the demo config with an `ApiKeyStore` bean reading from a database or key management service, with rotation/revocation and auditing. Real keys should be generated with `SecureRandom` and shown to the owner only once. Even if the key ID can be public, the secret portion must remain in a secret manager; never pass it via query strings or logs.

### Controller and Main Application

Create `ApiController.java`:

~~~java
package com.example.customauth;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/read")
    public String read(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Create `CustomAuthApplication.java`:

~~~java
package com.example.customauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }
}
~~~

For Spring Boot component scanning to pick up everything, place these classes in the same `com.example.customauth` package or subpackages of the `@SpringBootApplication` package. Runtime dependencies require `spring-boot-starter-web` and `spring-boot-starter-security`; tests require `spring-boot-starter-test` and `spring-security-test`.

### Running and Calling the API

Assuming a Spring Boot project with Maven Wrapper. On Unix/macOS:

~~~bash
export SPRING_PROFILES_ACTIVE=demo
export DEMO_API_KEY=client01.abcdefghijklmnopqrstuvwxyz012345
./mvnw spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/read
curl -i -H 'X-Api-Key: client01.abcdefghijklmnopqrstuvwxyz012345' \
  http://localhost:8080/api/read
~~~

Logical results with the demo:

- `GET /api/public`: returns `200`, body `public`.
- `GET /api/read` without key: returns `401` via the entry point.
- `GET /api/read` with valid demo key: returns `200`, body `svc-demo`.
- `GET /api/read` with wrong key: returns `401`.
- Calling `GET /api/read` without a key **after** a valid request still returns `401` because context is not persisted to subsequent requests.

Do not claim exact `curl -i` headers/stdout are identical across all environments; state only the status/body meaningful to the example flow. In production, avoid running `curl -v` or logging commands containing secrets to audit systems where the key could leak.

## 11. Integration Testing with MockMvc

Create `src/test/java/com/example/customauth/ApiKeyAuthenticationIntegrationTest.java`:

~~~java
package com.example.customauth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties =
    "DEMO_API_KEY=client01.abcdefghijklmnopqrstuvwxyz012345")
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class ApiKeyAuthenticationIntegrationTest {

    private static final String GOOD_KEY =
            "client01.abcdefghijklmnopqrstuvwxyz012345";

    @Autowired MockMvc mvc;
    @Autowired ApiKeyAuthenticationProvider provider;

    @Test
    void publicEndpointNeedsNoKey() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void validKeyAuthenticatesOnlyTheCurrentRequest() throws Exception {
        mvc.perform(get("/api/read").header("X-Api-Key", GOOD_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("svc-demo"));

        mvc.perform(get("/api/read"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidSecretsAndUnknownIdsAreRejected() throws Exception {
        mvc.perform(get("/api/read").header(
                "X-Api-Key",
                "client01.abcdefghijklmnopqrstuvwxyz012346"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/read").header(
                "X-Api-Key",
                "unknown1.abcdefghijklmnopqrstuvwxyz012345"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedAndDuplicateHeadersAreRejected() throws Exception {
        mvc.perform(get("/api/read")
                .header("X-Api-Key", "//bad.example"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/read")
                .header("X-Api-Key", GOOD_KEY, GOOD_KEY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unsupportedAuthenticationTypeIsNotClaimed() {
        assertFalse(provider.supports(
                UsernamePasswordAuthenticationToken.class));
    }

    @Test
    void callerCannotFlipAnUnverifiedTokenToAuthenticated() {
        ApiKeyAuthenticationToken input =
                ApiKeyAuthenticationToken.forRequest(GOOD_KEY);

        assertFalse(input.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> input.setAuthenticated(true));
    }
}
~~~

These tests actually traverse `FilterChainProxy`/the API filter/provider for `MockMvc` HTTP requests. They confirm:

1. Protected endpoints require a key while public endpoints remain accessible without one.
2. A valid secret maps to server principal `svc-demo`; a secret differing by one character is rejected.
3. A different key ID with the same secret cannot authenticate using the old ID's record.
4. Inputs failing regex or sending two headers are rejected.
5. Evidence does not persist across requests: each protected request must supply its key.
6. The provider does not claim to handle `UsernamePasswordAuthenticationToken`.
7. Callers cannot use `setAuthenticated(true)` on the input token themselves.

Run tests in a Maven Wrapper project:

~~~bash
./mvnw test
~~~

Do not fabricate fixed Maven stdout, because output depends on dependency versions, JDK, and environment.

### Adding Unit Tests for Status and Authorities

Using a mocked `ApiKeyStore` returning specific records, without HTTP:

~~~java
package com.example.customauth;

import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class ApiKeyProviderUnitTest {

    private static final String KEY =
            "client01.abcdefghijklmnopqrstuvwxyz012345";
    private static final String SECRET =
            "abcdefghijklmnopqrstuvwxyz012345";

    @Test
    void disabledOrExpiredCredentialCannotAuthenticate() {
        ApiKeyRecord expired = new ApiKeyRecord(
            "client01",
            "svc-demo",
            ApiKeyDigests.sha256(SECRET),
            true,
            Instant.parse("2000-01-01T00:00:00Z"),
            List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        ApiKeyRecord disabled = new ApiKeyRecord(
            "client01",
            "svc-demo",
            ApiKeyDigests.sha256(SECRET),
            false,
            Instant.parse("2099-01-01T00:00:00Z"),
            List.of(new SimpleGrantedAuthority("SCOPE_READ"))
        );

        ApiKeyAuthenticationProvider expiredProvider =
            new ApiKeyAuthenticationProvider(id -> Optional.of(expired));
        ApiKeyAuthenticationProvider disabledProvider =
            new ApiKeyAuthenticationProvider(id -> Optional.of(disabled));

        assertThrows(BadCredentialsException.class,
            () -> expiredProvider.authenticate(
                ApiKeyAuthenticationToken.forRequest(KEY)));
        assertThrows(BadCredentialsException.class,
            () -> disabledProvider.authenticate(
                ApiKeyAuthenticationToken.forRequest(KEY)));
    }
}
~~~

Real-world tests should also cover valid secrets with **insufficient authorities** (another endpoint requiring a higher scope → 403), keys revoked after previously being valid, multiple tenants, keys expiring right at the boundary, store timeouts, concurrent rotation, oversized headers, encoded Unicode, and high failure request rates. Tests must not log real keys or output digests into reports.

### Comparing Unit and Integration Tests

| Test | What It Proves | What It Does Not Prove |
| --- | --- | --- |
| `ApiKeyFormat.parse` unit | Input syntax is constrained. | That the key is security-valid. |
| `ApiKeyAuthenticationProvider` unit | Lookup, status, and digest comparison rules. | Filter order, HTTP status, or context lifecycle. |
| `MockMvc` integration | Servlet filter chain, authn, authz, and demo responses. | Production reverse proxy Host/TLS rules or real throughput. |
| Deployment test | HTTPS/proxy, secret rotation/revocation, real routing. | Long-term risk without monitoring/alerting. |

Never use a mock that "returns authenticated true for any input" and treat the provider as security-tested; there must be test cases proving **wrong credentials never yield an authenticated result**.

## 12. Standalone Java 17 Example: Format Validation Without Secret Verification

This code runs on JDK 17 without Spring and intentionally separates validation from verification. Create `ApiKeyFormatDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ApiKeyFormatDemo {

    private static final Pattern SHAPE = Pattern.compile(
        "([A-Za-z0-9_-]{8,32})\\.([A-Za-z0-9_-]{32,128})"
    );

    private static void inspect(String supplied) {
        if (supplied == null || supplied.length() > 161) {
            System.out.println("REJECT: invalid shape");
            return;
        }

        Matcher matcher = SHAPE.matcher(supplied);
        if (!matcher.matches()) {
            System.out.println("REJECT: invalid shape");
            return;
        }

        System.out.println("FORMAT_OK: keyId=" + matcher.group(1));
    }

    public static void main(String[] args) {
        inspect("client01.abcdefghijklmnopqrstuvwxyz012345");
        inspect("client01.short");
        inspect("client01.abcdefghijklmnopqrstuvwxyz012345.extra");
        inspect(null);
    }
}
~~~

Run:

~~~bash
javac ApiKeyFormatDemo.java
java ApiKeyFormatDemo
~~~

**Exact** stdout:

~~~text
FORMAT_OK: keyId=client01
REJECT: invalid shape
REJECT: invalid shape
REJECT: invalid shape
~~~

The program only confirms the input belongs to an allowed **syntactic language**; it does **not** look up the key ID, check expiry/enabled status, compare digests, or **grant permissions**. This is how to verify responsibility boundaries at the Java SE level before adding Spring.

## 13. If Authenticating OTPs Instead of API Keys

The provider model remains similar, but OTP security requirements differ significantly from long-lived API keys:

- OTPs must be bound to an account and a server-issued **challenge**; never accept just `username + 6-digit code` and trust the username.
- Enforce expiration, attempt limits, brute-force protection per account/IP/challenge, and **atomic mark-as-used** before accepting a one-time OTP.
- For TOTP, use a standard verifier with a bounded clock window, replay/step-reuse prevention, and a recovery process; never generate codes with plain `Random`.
- If OTP is a **second factor**, a valid OTP alone is **insufficient** to claim the user completed full MFA; the provider/flow must bind to the first authentication step and a trusted session/challenge.
- When combining multiple steps, you can use dedicated tokens representing temporary state, but never assign full authorities before all mandatory steps complete.
- OTPs are not like API keys: short secrets have low entropy, so do not copy the SHA-256 storage approach of long random API keys into an OTP store without rate limiting, short expiry, and anti-replay.

Similarly, if verifying JWTs, prefer standard `JwtDecoder`/providers; when writing a custom verifier, validate **signature, algorithm allowlist, issuer, audience, expiry, nbf, key rotation**, and relevant claims. `matches(regex)` on JWT structure is nowhere near enough.

## 14. Common Mistakes When Writing an AuthenticationProvider

### 14.1. Creating an Authenticated Token Before Verification

~~~java
// ANTI-PATTERN: never do this with untrusted input.
return ApiKeyAuthenticationToken.verified(
    request.getParameter("username"),
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

This is a **vulnerability illustration**, unusable as a standalone program because variables/imports are missing. If subject/permissions come from the client or skip verification, attackers can self-assign identities/privileges.

### 14.2. Overly Broad `supports(...)`

~~~java
@Override
public boolean supports(Class<?> type) {
    return true; // ANTI-PATTERN.
}
~~~

If a provider accepts every Authentication type yet casts `(ApiKeyAuthenticationToken) input`, it can throw `ClassCastException` or hijack unrelated flows. Accept only the exact token type. If multiple types are genuinely supported, define a clear contract for each.

### 14.3. Treating Format Validation as Authentication

`if (apiKey.matches("[A-Za-z0-9_.-]+")) return authenticated;` is wrong. Regex only checks syntax; it does not prove secret ownership, key status, permissions, or issuer.

### 14.4. Comparing Secrets with Plain String Equality

`raw.equals(storedSecret)` both requires storing plaintext secrets and can introduce timing issues. In the example, the store keeps digests and uses `MessageDigest.isEqual`. For user-entered passwords, use `PasswordEncoder.matches` rather than raw SHA-256.

### 14.5. Sending Internal Exception Messages to Clients

Never reflect key IDs, secrets, existence status, or stack traces. Cases like "unknown key", "wrong secret", and "revoked key" can share a generic HTTP message, while internal telemetry records desensitized error codes. Prevent user/key enumeration.

### 14.6. Catching All Exceptions and Allowing Through

Code like `catch (Exception ex) { return ApiKeyAuthenticationToken.verified(...); }` is a dangerous fail-open flaw. DB errors, parse failures, and timeouts must fail closed without granting a result. Nor should infrastructure errors be disguised as "wrong user password" and suppress operational alerts.

### 14.7. Mixing Client Roles with Database Roles

Never take `X-Role: ADMIN` or JSON `roles=["ADMIN"]` as authorities in the result. Permissions must come solely from server-managed policies/stores; every request must still pass through separate authorization.

### 14.8. Double-Registering a Custom Filter

A filter defined as a Spring bean can be auto-registered by Boot into the servlet container **and** added to the Spring Security chain. Result: running out of order or twice, producing unpredictable behavior. In the example, the filter is not a bean and is instantiated with `new` solely inside `apiChain`.

### 14.9. Confusing AuthenticationProvider with AuthenticationManager

A provider knows **how to verify one token type**. The manager coordinates providers. Filters call the manager, not individual providers directly. With multiple chains, verify the specific chain's manager/providers and ensure no fallback path mis-accepts the token.

### 14.10. Writing Credentials into Logs or Response Headers

Never log full request headers, `Authentication.getCredentials()`, API keys, hashes, secrets, or session cookies. You can still log correlation IDs, provider types, high-level failure reasons, and key IDs handled per security policy; never log raw secrets.

### 14.11. Forgetting Status and Revocation

A key whose digest matches yet is disabled/expired/revoked must be rejected. If caching is used, implement invalidation/TTL and revocation propagation plans. Distinguish between a key being *granted access* and a key remaining *technically valid*.

### 14.12. Reading SecurityContext on the Wrong Thread

`SecurityContextHolder` is thread-bound by default. Do not assume an `@Async`/`CompletableFuture` task automatically inherits the request's context. Proper propagation and cleanup are required; in background systems, prefer dedicated machine/service identities rather than passing raw API keys across executors.

## 15. Operational and Testing Design Beyond the Example

**Key lifecycle.** Provide `SecureRandom` generation, one-time secret display, digest storage, subject/scope assignment, expiration, bounded overlapping rotation, disable/revoke, auditing, and timely deletion of old keys. With multi-tenancy, unique IDs and permissions must bind to a trusted tenant source.

**Latency.** Fast lookup via indexed key ID; bound input length before hitting the DB; rate limit per client/key ID/IP appropriately; avoid expensive password-hashing work factors on every 256-bit API key unless architecture requires it. For weak/low-entropy credentials, the threat model is completely different.

**Host/proxy assumptions.** Serve the API over HTTPS and control trusted proxies and forwarding. Never read user identity from `X-Forwarded-User` or similar headers arriving from the Internet without an authenticating gateway and a verified trust boundary.

**Error reporting.** Invalid credentials usually yield 401; missing permissions usually yield 403. Never allow returning HTTP 200 with a client-controlled `authenticated=true` object. On DB errors, treat service availability as a system error and trigger alerts without leaking secrets.

**Security metrics.** Track 401/403 rates, rejections from malformed/duplicate headers, key expiry/revocation events, provider latency, and key update counts. Never attach raw API keys to metric labels, which exposes secrets and causes high cardinality.

### Suggested Test Matrix

| Case | Expectation |
| --- | --- |
| Missing header on public endpoint | 200 if policy is permitAll. |
| Missing header on protected endpoint | 401, no authenticated principal. |
| Malformed, oversized, or newline-containing header | 401, no store query when parser fails. |
| Two `X-Api-Key` headers | 401, do not arbitrarily use the first value. |
| Existing key ID, wrong secret | 401; no authorities granted. |
| Non-existent key ID | 401; do not reveal whether ID exists. |
| Disabled, expired, or revoked key | 401 even if secret matches. |
| Valid key, sufficient scope | 200; principal comes from store. |
| Valid key, insufficient scope | 403; authentication succeeds but authorization denies. |
| Subsequent request without key | Does not reuse previous request's principal. |
| Store timeout | Fail closed; emit metric/alarm and appropriate response, never bypass. |
| Two security chains | Request hits the right chain and provider; not mis-handled by fallback provider. |
| Secret credential appears in logs | Tests/log reviews must catch and eliminate it. |

## 16. Checklist and Self-Check

**Pre-release checklist:**

- [ ] Concrete reason exists to write a custom provider instead of `DaoAuthenticationProvider`, JWT decoder, or built-in mechanisms.
- [ ] `supports(Class<?>)` accepts only the exact token type.
- [ ] Authentication requests created by the filter start with `isAuthenticated()==false` and no client-supplied authorities.
- [ ] Validator bounds size and format before performing expensive I/O.
- [ ] Verifier checks secrets using an algorithm/mechanism suited to entropy, along with enabled, expiry, and revocation checks.
- [ ] Principal and authorities are loaded from a server source after verification.
- [ ] Provider throws `AuthenticationException` on invalid evidence; never builds an authenticated result if verification fails.
- [ ] Filter invokes `AuthenticationManager` instead of querying DBs/comparing hashes in place of the provider.
- [ ] SecurityContext lives strictly for the request scope and is cleaned up.
- [ ] Filter is not double-registered across Boot and the security chain.
- [ ] HTTPS and secret protection across logs, config, database, requests, and responses.
- [ ] Tests cover validation, provider, HTTP filter, status/authorities, and multiple requests.
- [ ] Key rotation, revocation, auditing, and safe infrastructure error handling are in place.

**Q1. Does `supports(...)` returning true mean the credential is valid?** No. It only indicates the provider can handle that **token class**. `authenticate(...)` performs the actual verification.

**Q2. Is regex validation enough to authenticate an API key?** No. Regex checks structure only; you still must query the key store, check expiry/revocation, and verify the secret.

**Q3. Why not let the filter set `isAuthenticated=true` directly from a header?** Because headers are client-controlled; only a trusted provider/verifier may create an authenticated result after succeeding.

**Q4. Can `SHA-256` be used for API key secrets?** It can be suitable for **very high-entropy random** secrets. Do not apply it to human-chosen passwords; passwords require dedicated KDFs with work factors.

**Q5. Why are `401` and `403` different?** `401` indicates missing/invalid authentication; `403` indicates authenticated identity lacking permission under authorization policy.

**Q6. Why isn't `ApiKeyHeaderFilter` annotated with `@Component` in the example?** To prevent Boot from auto-registering it as a container filter outside the security chain when already added via `http.addFilterBefore(...)`.

**Q7. Does one valid request automatically authenticate the next request?** Not in the stateless API here. The next request must supply the key; the previous context is cleared and not stored in a session.

**Q8. If an OTP is only six digits, can it use the same hashing/API-key strategy?** No. OTPs have low entropy and require challenge binding, short expiry, rate limiting, and replay protection; do not copy assumptions meant for long random API keys.

**Remember:** **Filter reads input → unauthenticated token → manager selects provider → provider checks format + trusted source + evidence + status → authenticated token → context → authorization**. Specifically, **"syntactically valid data" does not mean "authenticated identity"**.
