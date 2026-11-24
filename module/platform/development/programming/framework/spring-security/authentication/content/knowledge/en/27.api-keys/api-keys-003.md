# Custom Provider or AuthenticationManager for Validating API Keys in Spring Security

## 1. Goal and problem statement

An internal API or machine-to-machine integration typically receives an **API key** in an HTTP header to identify the client. There is no login form, no browser session, and not necessarily an end user. The Spring Security application must turn a client-provided secret string into a **verified Authentication**, then decide which APIs the client is allowed to call.

This lesson explains how to structure a **custom AuthenticationProvider** or a **dedicated AuthenticationManager**, placed after a filter that extracts the API key and before Spring Security's authorization layer. The focus includes:

1. Distinguishing the responsibilities of `Filter`, `AuthenticationManager`, `AuthenticationProvider`, `Authentication`, and `SecurityContext`.
2. Designing an API key as a bearer credential with owner identity, status, permissions, expiration, and revocation lifecycle.
3. Choosing properly between using an `AuthenticationProvider` inside `ProviderManager` and using an `AuthenticationManager` directly.
4. Writing a runnable **Java 17+ / Spring Boot Servlet** example, from HTTP request to **401 Unauthorized** or **403 Forbidden** status.
5. Testing missing key, invalid key, valid key, and valid-key-without-permission scenarios.
6. Recognizing dangerous mistakes: hardcoded keys, unchecked string comparisons, leaking keys in logs, misusing sessions, granting permissions from untrusted headers, and lacking a rotation process.

**An API key is not a user password, an OIDC ID Token, a JWT, or a standard delegation mechanism.** It is a secret that the server must verify; whoever possesses that secret can typically act as the client bound to the key. Therefore, it requires TLS, secret management, and scoped permissions just like any bearer credential.

## 2. Architecture from header to Authentication

```text
HTTP client
    |
    | GET /api/whoami
    | X-API-Key: <secret>
    v
Spring Security FilterChainProxy / SecurityFilterChain
    |
    | ApiKeyAuthenticationFilter (custom OncePerRequestFilter)
    |   - read exactly one header value
    |   - check input format / size
    |   - create ApiKeyAuthenticationToken (unauthenticated)
    |
    | AuthenticationManager.authenticate(token)
    |   |
    |   +-- ProviderManager
    |         |
    |         +-- ApiKeyAuthenticationProvider
    |                - accept matching token type
    |                - look up/match API key hash
    |                - check revoked/expired/active
    |                - load clientId, authorities
    |                - return authenticated Authentication
    |
    | SecurityContextHolder
    |   - attach authenticated Authentication to request
    |
    | AuthorizationFilter
    |   - authenticated(), hasAuthority("API_ADMIN"), ...
    v
Controller / Service -> result
```

A request has three primary outcomes:

| Scenario | Outcome | Reason |
| --- | --- | --- |
| Missing key, wrong key, or revoked key | **401** | No valid Authentication |
| Valid key but client lacks required authority | **403** | Authenticated, permission denied |
| Valid, active key with appropriate authority | **2xx** if processing succeeds | Authenticated and permitted |

In practice, the status can be customized by `AuthenticationEntryPoint`/`AccessDeniedHandler` or organizational policy. The example below configures the 401 path explicitly.

### 2.1. Why not check directly inside every controller?

If every controller wrote:

```java
if (!"secret".equals(request.getHeader("X-API-Key"))) {
    // return error
}
```

it would be very easy to miss protecting an endpoint, leak secrets in source code, complicate auditing, and fragment authorization handling. Moving verification into an authentication filter + provider ensures every request within `/api/**` goes through the same contract.

### 2.2. What responsibility does each component take?

| Component | Responsibility | Should not do |
| --- | --- | --- |
| `OncePerRequestFilter` | Extract header, create authentication request, call manager, handle failure | Check permissions inside every controller or set `authenticated=true` before verification |
| `AuthenticationManager` | Coordinates a single authentication attempt; usually `ProviderManager` | Be mistaken for a key storage repository |
| `AuthenticationProvider` | Verifies a specific `Authentication` type and issues principal/authorities | Trust permissions self-declared by the client in headers |
| `Authentication` | Represents an unauthenticated request or an authenticated result | Retain the raw API key inside the principal after authentication |
| `SecurityContextHolder` | Holds the current request's context in the Servlet stack | Act as login state storage across stateless requests |
| `SecurityContextRepository` | Defines how context is loaded/saved across requests when needed | Force session persistence for every API |
| `AuthorizationFilter` | Evaluates rules such as `hasAuthority(...)` | Verify API key secrets in place of the provider |

**Design rule:** the filter passes an **untrusted credential** into the manager; the provider returns a **server-determined principal and permissions**; only then does the filter place the result into `SecurityContextHolder`. Spring Security can continue handling authorization just as with other authentication mechanisms.

## 3. Contract of AuthenticationProvider and ProviderManager

`AuthenticationProvider` in Spring Security has two methods:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

This is a condensed API signature, **not a standalone Java class**.

- `supports(...)` returns `true` when the provider can handle the given token class, such as `ApiKeyAuthenticationToken.class`.
- `authenticate(...)` receives a token containing the **unverified raw key**; if the key is valid, it creates a **new** Authentication with a trusted principal/authorities.
- When the key is invalid, throw `BadCredentialsException` or an appropriate `AuthenticationException`. Never turn an invalid key into an anonymous-but-successful user.
- When the provider cannot handle the Authentication type, it may return `null` so the manager tries another provider. In the example, the provider serves only one token type.
- `ProviderManager` delegates the authentication request through a list of providers, handles results/errors, and supports erasing credentials from the authentication result according to policy.

Thus the architectural snippet takes the form:

```java
AuthenticationManager manager =
    new ProviderManager(apiKeyAuthenticationProvider);

Authentication result = manager.authenticate(
    new ApiKeyAuthenticationToken(rawKey));
```

This is an **illustrative snippet**; the `ApiKeyAuthenticationToken` class and provider are fully defined in section 6.

**Do not confuse `supports()` with authorization.** `supports(ApiKeyAuthenticationToken.class) == true` only means the provider **knows how to check that token type**; it does not prove the key is valid and does not authorize an admin endpoint.

### Provider or custom AuthenticationManager?

| Option | Suitable when | Notes |
| --- | --- | --- |
| **Custom `AuthenticationProvider` + `ProviderManager`** | You want standard mechanics and possibly combining with other authentication types | Easy to unit test provider, clear `supports()`, extensible |
| **Custom `AuthenticationManager`** | A security chain truly has only one custom verification logic, e.g., calling a centralized key verification service | Simpler for small flows; directly responsible for auth contract, errors, and secret lifecycle |
| **`AuthenticationManagerResolver<HttpServletRequest>`** | Need to choose different managers per verified host/tenant/issuer/request, e.g., multiple independent auth zones | Must avoid choosing a manager from client-controlled headers without verifying the trust boundary |

There is no need to write a custom manager and wrap it in a provider just to rename classes. **One manager with one clear provider is enough** for this example. If an API uses multiple authentication methods, separate `SecurityFilterChain`/matchers or scope providers/managers carefully, avoiding a weak mechanism becoming a bypass into a high-protection endpoint.

## 4. Designing the API key properly before writing code

A secure API key typically has **two sides**:

- **Secret value:** a high-entropy random string kept confidential by the client, sent in `X-API-Key` or a well-defined authentication header. Anyone holding the secret can use it.
- **Server-side record:** key ID, owner client/service ID, digest/credential verifier, authorities, issuance/expiration timestamps, revoked status, audit metadata, rotation policy, and quota/rate limits.

A real-world record might look like:

```text
key_id          = ak_2026_001               # public lookup identifier
client_id       = billing-exporter           # service principal
secret_digest   = SHA256(secret)             # demo: 256-bit random secret
authorities     = [API_READ]
created_at      = 2026-11-01T00:00:00Z
expires_at      = 2027-02-01T00:00:00Z
revoked_at      = null
enabled         = true
```

In production, choose a random secret with at least ~128-bit entropy (e.g., 32 random bytes = 256 bits), display the plaintext **once at issuance**, and store only the verifier. For machine-generated high-entropy secrets, SHA-256/HMAC-SHA-256 can be appropriate; **if the secret is user-chosen with low entropy**, you must use a protective design like a password KDF (Argon2id/bcrypt/scrypt) or avoid turning it into an API key. HMAC with a server-side pepper adds a layer of protection for hashed data if the DB is leaked.

You should have a **key prefix / key ID** to select the verification record, e.g., `ak_live_<public-id>.<random-secret>`; store the public ID and secret digest separately. The example below scans two in-memory digests to illustrate the provider, **not a lookup design suitable for millions of keys**.

### Important constraints

1. **Never store plaintext** in databases, source code, committed config, or logs.
2. **Never read authorities from headers** such as `X-Role: ADMIN` supplied by the client. Authorities must come from the server-side key record.
3. **Do not equate a key with an end-user identity.** Usually authenticate as a service/client principal. If "on behalf of user" is required, use OAuth/OIDC or an appropriate delegation mechanism.
4. **Do not rely solely on key prefixes.** Prefixes are for lookup/display, not proof of authentication.
5. **Multiple keys per client during rotation:** allow issuing a new key, transitioning during a controlled overlap window, then revoking the old key.
6. **Revocation and expiration:** check on every request or use a cache with a short TTL / proper invalidation strategy.
7. **Least-privilege scopes/authorities:** e.g., a reporting client gets `API_READ`, while a separate operations client also gets `API_ADMIN`.
8. **Mandatory TLS** on every hop; keys must never be placed in query strings because URLs are often logged, cached, and leaked via referrers.
9. **Abuse prevention:** rate limiting, quotas, auditing by `client_id/key_id`, anomaly detection, and rotation alerts.
10. **Fail-closed configuration** when the key store is unreachable. Never "temporarily allow" requests due to a dependency failure.

## 5. Per-request processing flow and SecurityContext

Example request:

```http
GET /api/whoami HTTP/1.1
Host: api.example.com
X-API-Key: <random-secret>
```

Inside `doFilterInternal(...)`:

1. Confirm the path falls under API key scope, e.g., `/api/**`.
2. Read the header. If missing, duplicated, or malformed → return 401 via `AuthenticationEntryPoint` without forwarding the request to the controller.
3. Create an unauthenticated `ApiKeyAuthenticationToken`; `getCredentials()` holds the raw key and `isAuthenticated() == false`.
4. `AuthenticationManager.authenticate(...)` invokes the matching provider. The provider compares the digest against the server-side verifier, checks status, and returns an Authentication with `principal="report-reader"` and `API_READ`.
5. The filter creates a new `SecurityContext` and sets the result in `SecurityContextHolder` **for the current request**.
6. Call `filterChain.doFilter(...)` so Spring continues with authorization and the controller.
7. Always clear the context in `finally` to prevent leaking authentication to another request when the server reuses threads.

**Why must the filter handle `AuthenticationException` itself?** A custom authentication filter is placed **before `ExceptionTranslationFilter`** in the SecurityFilterChain. Exceptions thrown before that filter generally cannot rely on the downstream `ExceptionTranslationFilter` to catch them. Therefore, the example catches errors from `manager.authenticate(...)` and invokes `AuthenticationEntryPoint` directly, while downstream authorization errors are handled by Spring Security.

**Stateful or stateless?** API keys normally authenticate **per request** without needing session cookies. The example below uses `SessionCreationPolicy.STATELESS` with `NullSecurityContextRepository`: do not save `Authentication` into an HTTP session. One successful authentication does not allow a subsequent request without a key.

## 6. Runnable Spring Boot Java 17+ example

This sample demonstrates **Spring Boot 3.5.16, Spring Security 6.x, Servlet/Spring MVC**. Boot 3.5.16 is pinned for reproducible lab practice; the 3.5 line has reached end of OSS support, so new systems should choose a currently supported branch and adjust APIs to match that version.

Design highlights:

- Two **64-hex-character** API keys generated from 32 random bytes, provided via environment variables (no committed secrets).
- The provider hashes keys with SHA-256 and compares digests, never storing plaintext as a constant in source code.
- `report-reader` has `API_READ`; `ops-admin` has `API_READ` and `API_ADMIN`.
- The filter protects all requests under `/api/**`; `/public` requires no key.
- To keep the example focused on authentication, only GET endpoints are included. If POST/PUT/DELETE endpoints are added later, CSRF must be designed according to whether cookies or header-only auth are used, rather than disabling all protection unconditionally.

Structure:

```text
api-key-demo/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/apikey/ApiKeyDemoApplication.java
└── src/test/java/demo/apikey/ApiKeyDemoApplicationTests.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>api-key-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Only Spring Security core/web via starters are needed. **There is no mandatory official API key starter** for this custom provider; `AuthenticationProvider`, `ProviderManager`, `AbstractAuthenticationToken`, and `OncePerRequestFilter` are already included in the dependencies above.

### 6.2. `application.yml`

```yaml
app:
  api-key:
    user: "${APP_API_KEY_USER}"
    admin: "${APP_API_KEY_ADMIN}"

server:
  port: 8080
```

The application will fail to start if the required environment variables are missing. Production deployments can use a secret manager, database, or KMS instead of these two demo variables; never put secrets in the repository.

### 6.3. A complete Java file containing Filter, Provider, and Manager

Create `src/main/java/demo/apikey/ApiKeyDemoApplication.java`:

```java
package demo.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Enumeration;
import java.util.List;
import java.util.Collection;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}

@Configuration
class ApiKeySecurityConfig {

    @Bean
    ApiKeyProvider apiKeyProvider(
            @Value("${app.api-key.user}") String userKey,
            @Value("${app.api-key.admin}") String adminKey) {
        return new ApiKeyProvider(userKey, adminKey);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ApiKeyProvider provider) throws Exception {

        // DEDICATED manager for key-based authentication.
        AuthenticationManager manager = new ProviderManager(provider);
        AuthenticationEntryPoint entryPoint =
            new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        // Do not declare this filter as a @Bean: Boot may register
        // it outside Spring Security and run it twice.
        ApiKeyFilter apiKeyFilter = new ApiKeyFilter(manager, entryPoint);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasAuthority("API_ADMIN")
                .requestMatchers("/api/**").hasAnyAuthority(
                    "API_READ", "API_ADMIN")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                apiKeyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}

/**
 * Pre-authentication token: principal=null, credentials=raw key.
 * Post-authentication token: principal=service ID, credentials=null,
 * authorities granted by the server.
 */
final class ApiKeyToken extends AbstractAuthenticationToken {

    private final String principal;
    private String key;

    ApiKeyToken(String presentedKey) {
        super(null);
        this.principal = null;
        this.key = presentedKey;
        super.setAuthenticated(false);
    }

    private ApiKeyToken(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        super(authorities);
        this.principal = principal;
        this.key = null;
        // Internal factory only after the provider has verified.
        super.setAuthenticated(true);
    }

    static ApiKeyToken authenticated(
            String principal,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyToken(principal, authorities);
    }

    @Override
    public Object getCredentials() {
        return key;
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.key = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Unverified API key cannot be marked authenticated");
        }
        super.setAuthenticated(false);
    }
}

/**
 * Demo: two verifiers stored in memory.
 * Production: look up key record by keyId; check expiry/revocation.
 */
final class ApiKeyProvider implements AuthenticationProvider {

    private static final Pattern HEX_256 =
        Pattern.compile("[0-9a-f]{64}");

    private final List<ClientRecord> clients;

    ApiKeyProvider(String readerSecret, String adminSecret) {
        byte[] readerHash = digest(validSecret(readerSecret));
        byte[] adminHash = digest(validSecret(adminSecret));
        if (MessageDigest.isEqual(readerHash, adminHash)) {
            throw new IllegalArgumentException(
                "Reader and admin API keys must be different");
        }
        clients = List.of(
            new ClientRecord(
                "report-reader",
                readerHash,
                List.of(new SimpleGrantedAuthority("API_READ"))),
            new ClientRecord(
                "ops-admin",
                adminHash,
                List.of(
                    new SimpleGrantedAuthority("API_READ"),
                    new SimpleGrantedAuthority("API_ADMIN")))
        );
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof ApiKeyToken token)
                || token.isAuthenticated()) {
            throw new BadCredentialsException("Invalid API key");
        }
        String raw = (String) token.getCredentials();
        if (raw == null || !HEX_256.matcher(raw).matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        byte[] presentedDigest = digest(raw);
        ClientRecord match = null;

        // Do not short-circuit when comparing multiple verifiers in a small demo.
        for (ClientRecord record : clients) {
            if (MessageDigest.isEqual(
                    presentedDigest, record.secretDigest())) {
                match = record;
            }
        }
        if (match == null) {
            throw new BadCredentialsException("Invalid API key");
        }
        return ApiKeyToken.authenticated(
            match.clientId(), match.authorities());
    }

    @Override
    public boolean supports(Class<?> type) {
        return ApiKeyToken.class.isAssignableFrom(type);
    }

    private static String validSecret(String raw) {
        if (raw == null || !HEX_256.matcher(raw).matches()) {
            throw new IllegalArgumentException(
                "API key must be 64 lowercase hexadecimal characters");
        }
        return raw;
    }

    private static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private record ClientRecord(
        String clientId,
        byte[] secretDigest,
        List<GrantedAuthority> authorities) {}
}

final class ApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-API-Key";
    private static final Pattern HEX_256 =
        Pattern.compile("[0-9a-f]{64}");

    private final AuthenticationManager manager;
    private final AuthenticationEntryPoint entryPoint;

    ApiKeyFilter(
            AuthenticationManager manager,
            AuthenticationEntryPoint entryPoint) {
        this.manager = manager;
        this.entryPoint = entryPoint;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return !(path.equals("/api") || path.startsWith("/api/"));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders(HEADER);
        if (!values.hasMoreElements()) {
            reject(request, response);
            return;
        }

        String key = values.nextElement();
        if (values.hasMoreElements() ||
                !HEX_256.matcher(key).matches()) {
            // Reject duplicate or malformed header; do not log raw key.
            reject(request, response);
            return;
        }

        Authentication result;
        try {
            result = manager.authenticate(new ApiKeyToken(key));
        } catch (AuthenticationException failure) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, failure);
            return;
        }

        try {
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(result);
            SecurityContextHolder.setContext(context);
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private void reject(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        SecurityContextHolder.clearContext();
        entryPoint.commence(
            request, response, new BadCredentialsException("Invalid API key"));
    }
}

@RestController
class ApiKeyController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin-ok";
    }
}
```

**Reading the code along the data path:**

- `ApiKeyFilter` is the HTTP boundary layer. It accepts only a single header matching the 64-hex-character format, without echoing or logging the value.
- `ApiKeyToken` protects the boundary between **unauthenticated** and **authenticated** tokens; callers cannot simply invoke `setAuthenticated(true)` to bypass the provider.
- `ApiKeyProvider` compares the SHA-256 digest of a high-entropy key against verifiers built at startup. It returns **server-assigned** principal and authorities, never client-supplied ones.
- `new ProviderManager(provider)` is the dedicated AuthenticationManager for the API key filter. If the provider throws `AuthenticationException`, the filter invokes `AuthenticationEntryPoint` to return HTTP 401.
- `SecurityContext` is populated for the request and cleared in `finally`; authentication is not persisted to an HTTP session between requests.
- `hasAuthority("API_ADMIN")` runs **after** authentication; `report-reader`'s key succeeds on `/api/whoami` but is rejected on `/api/admin`.
- `ApiKeyFilter` is instantiated inside the security config method, so it does not become a Spring `Filter` bean auto-registered twice by Boot.

**Example limitations:** this is an in-memory store with only two keys and no support for revocation, expiry, auditing, or rotation. Production designs must extend the provider to look up a DB/secret service and verify key status. Do not treat plain `SHA-256` as a safe solution for low-entropy secrets.

## 7. Running from the terminal

On a machine with OpenSSL, generate two **distinct random** secrets (Bash syntax):

```bash
export APP_API_KEY_USER="$(openssl rand -hex 32)"
export APP_API_KEY_ADMIN="$(openssl rand -hex 32)"

mvn spring-boot:run
```

The application uses environment variables for the two keys. Never print keys to shared terminals, commit shell scripts containing them, or take screenshots of secrets. In real systems, provision keys via a secret management workflow.

In a terminal **sharing the same environment variables** (or injecting the variables via an appropriate secure channel):

```bash
# Public endpoint
curl -s http://localhost:8080/public

# Reader allowed on /api/whoami
curl -s -H "X-API-Key: $APP_API_KEY_USER" \
  http://localhost:8080/api/whoami

# Admin allowed on /api/admin
curl -s -H "X-API-Key: $APP_API_KEY_ADMIN" \
  http://localhost:8080/api/admin

# Missing key -> 401
curl -i http://localhost:8080/api/whoami

# Reader lacks admin permission -> 403
curl -i -H "X-API-Key: $APP_API_KEY_USER" \
  http://localhost:8080/api/admin

# Invalid key -> 401
curl -i -H "X-API-Key: invalid" \
  http://localhost:8080/api/whoami
```

Bodies of the first three requests, in order:

```text
public
report-reader
admin-ok
```

The next three commands receive **401**, **403**, and **401** respectively. Depending on how Spring Boot renders errors, headers and bodies may vary; the HTTP status code is the behavior to verify. `curl -s` does not append a newline, so consecutive calls may print output on the same line.

**Syntax note:** a Bash export in one terminal does not propagate to another terminal. When running `curl` in a new window, provide the same secret via a secure mechanism; otherwise `$APP_API_KEY_USER` is empty and the request will be rejected. Never record secrets into shell history as literal commands with fixed values.

## 8. Testing with MockMvc without real keys

Create `src/test/java/demo/apikey/ApiKeyDemoApplicationTests.java`:

```java
package demo.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyDemoApplicationTests {

    // DUMMY test-only secrets, never use to protect a service.
    private static final String READER_KEY = "a".repeat(64);
    private static final String ADMIN_KEY = "b".repeat(64);

    @DynamicPropertySource
    static void testKeys(DynamicPropertyRegistry registry) {
        registry.add("app.api-key.user", () -> READER_KEY);
        registry.add("app.api-key.admin", () -> ADMIN_KEY);
    }

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoKey() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void readerKeyBecomesServerOwnedPrincipal() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("report-reader"));
    }

    @Test
    void adminAuthorityIsCheckedAfterAuthentication()
            throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .header("X-API-Key", ADMIN_KEY))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));
    }

    @Test
    void missingInvalidAndDuplicateKeysAreRejected()
            throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                .header("X-API-Key", "bad"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY, ADMIN_KEY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aNewRequestMustPresentItsOwnKey() throws Exception {
        mvc.perform(get("/api/whoami")
                .header("X-API-Key", READER_KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
mvn test
```

The expected result is **5 passing tests** if dependencies download successfully. The tests exercise the full path Spring MVC → SecurityFilterChain → filter → manager → provider → authorization → controller using two test secrets.

**Do not confuse test scope:** MockMvc only verifies application logic. It does not prove that the reverse proxy protects headers, traffic uses TLS, real-world API keys are randomly issued, or database revocation/rotation works. Those requirements need corresponding integration/security tests.

## 9. Writing a custom AuthenticationManager instead of a Provider

A custom `AuthenticationManager` is valid when you do not want a provider chain, for example when all authentication is handled by a dedicated key verification service.

Core signature:

```java
Authentication authenticate(Authentication request)
    throws AuthenticationException;
```

Conceptual example:

```java
AuthenticationManager manager = request -> {
    if (!(request instanceof ApiKeyToken token)) {
        throw new ProviderNotFoundException(
            "Unsupported authentication type");
    }
    return apiKeyVerificationService.authenticate(
        (String) token.getCredentials());
};
```

This is an **architectural snippet**, not a standalone program. `apiKeyVerificationService` is a custom abstraction that must **actually verify** the secret, status, expiration, and permissions and return a safe `Authentication`; `ProviderNotFoundException` must be imported from `org.springframework.security.authentication`. Never implement `authenticate(...)` by simply calling `ApiKeyToken.authenticated("admin", ...)` for arbitrary raw input.

**When to prefer a Provider?** When the codebase already uses `ProviderManager`, supports multiple credential types, needs explicit `supports()`, or wants to swap key store implementations without changing the filter. **When does a direct manager make sense?** An independent mechanism verified by an external/dedicated system with fail-closed steps thoroughly tested.

For multi-tenancy, you can configure multiple `SecurityFilterChain` beans or an `AuthenticationManagerResolver<HttpServletRequest>`. Select the manager using a trusted source (hostname/tenant bound at the gateway, client registration, etc.), **never blindly trust an `X-Tenant: admin` header to pick a weaker manager**.

## 10. Upgrading the provider for production

### 10.1. Key storage model

An illustrative database schema:

```sql
CREATE TABLE api_client (
    id UUID PRIMARY KEY,
    client_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE api_key (
    id UUID PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES api_client(id),
    public_key_id VARCHAR(80) NOT NULL UNIQUE,
    secret_digest VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE api_client_authority (
    client_id UUID NOT NULL REFERENCES api_client(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (client_id, authority)
);
```

This is a reference schema, without a generator or key issuance service. Choose timestamp types, indexes, auditing, and tenant columns appropriate for your real database. Avoid synchronous `last_used_at` updates on every high-load request if it causes lock contention; batch or event-aggregate them instead.

Provider flow in production:

1. Parse a single header, enforcing length limits and allowed characters.
2. Extract the **public key ID** (not the raw secret) if the key format includes a prefix/ID.
3. Look up the exact record in the trusted store; if missing, reject.
4. Compute the digest/HMAC of the secret portion and compare against the verifier with a timing-resistant comparison function; never log the value.
5. Check `enabled`, `revoked_at`, `expires_at`, and parent client status.
6. Load authorities/tenant constraints from server-side policies.
7. Return an Authentication containing a stable `clientId/keyId`, **without the secret**.
8. Update audits/metrics separately without excessively slowing down the auth path; store errors must fail closed.

A key may carry multiple permissions, yet all services should never share one common key. Tying audits to a specific owner enables revoking only the compromised client without disrupting the entire system.

### 10.2. Key rotation, revocation, and expiry

Example zero-downtime rotation flow:

```text
T0: Key A active -> client uses A
T1: Issue new Key B with same client and required permission scope
T2: Client deploys B, confirm traffic moves to B
T3: Revoke A; A immediately returns 401 per status check policy
T4: Clean up old hashes/audits after retention period
```

If the provider caches key status, `revoke A` may **not take effect immediately** unless the cache is invalidated. Design TTLs/cache versions or event invalidation to match security requirements. Never use an unbounded application session to "remember" an authenticated API key.

### 10.3. Client and tenant key policies

- Evaluate authorities at both API path and resource/tenant level. Having `API_READ` does not mean reading every tenant's data.
- Follow least privilege; separate sandbox and production keys, and separate read-only and write/admin keys.
- Restrict IPs/ASNs/networks when appropriate, yet **an IP allowlist does not replace a key secret**, especially behind a reverse proxy.
- For critical service-to-service traffic, consider **mTLS, OAuth2 Client Credentials, or signed requests** if stronger protection against replay/credential forwarding than plain bearer API keys is needed.
- If a gateway verifies API keys and passes client identity to Spring, the backend needs a clear trust boundary (mTLS/network isolation/header stripping) and may use pre-auth instead of re-checking the raw key.

### 10.4. HTTP, proxies, and logging

Never accept API keys in query strings or URL paths. The `X-API-Key` header can still leak if gateway/access logs record full headers: configure **redaction** in proxies, app logs, APM, tracing, error reporting, and support tooling.

Do not return `"unknown key ID"` or `"expired key for customer X"` to unauthenticated clients if it leaks sensitive data. External responses should consistently return 401; the server logs detailed reasons in controlled logs without recording the secret.

Bearer API keys can be replayed if exposed. Enforce full TLS, restrict where keys can be used, and apply short lifetimes and quotas commensurate with risk. For scenarios requiring per-request replay protection, add request signatures (timestamp/nonce) or a properly standardized and verified protocol, not merely an unsigned timestamp.

## 11. Notes on CSRF, sessions, and separating SecurityFilterChains

In the example, API endpoints use only GET and a header key; CSRF does not block reads by default. When adding state-changing HTTP methods, clarify whether clients are **browsers using cookies** or **machines using header API keys**.

If an entire chain accepts only header-based API keys actively sent by programmatic clients and **does not use browser cookies/sessions for authentication**, disabling CSRF specifically for those API matchers can be considered. If the same application also has form login, cookies, or a session-based SPA, keep CSRF enabled for browser routes; never use global `csrf.disable()` just to silence an unanalyzed 403 error.

An application may have:

- `/api/**` chain: stateless, authenticated with API keys or bearer tokens per policy.
- `/web/**` chain: session/cookie, OIDC login, CSRF enforced.
- Health/public endpoints: explicitly scoped and permitted.

When multiple chains exist, use `@Order` and `securityMatcher(...)` in the right order; each request is typically handled by the **first matching SecurityFilterChain**, so avoid a `permitAll` chain accidentally shadowing an API-protecting chain. When terminating API keys at an upstream gateway, never treat `X-Forwarded-*` or `X-Client-Id` from untrusted networks as authentication results.

## 12. Common issues and troubleshooting

| Symptom | Typical cause | Resolution |
| --- | --- | --- |
| Request without key returns 200 | Filter missing from chain, matcher misses path, or `permitAll` rule is too broad | Inspect SecurityFilterChain, URL mappings, and filter invocation |
| Any key is accepted | Provider does not actually verify, or sets `authenticated=true` from raw header | Verify digest before creating an authenticated token |
| Invalid key causes 500 instead of 401 | Filter lets `AuthenticationException` escape before `ExceptionTranslationFilter` | Catch exception in auth filter and invoke `AuthenticationEntryPoint` |
| Valid key returns 403 | Wrong authority, missing role, or endpoint requires different policy | Check `hasAuthority(...)` and server-side mapping |
| Invalid key keeps previous request's user | `SecurityContextHolder` not cleared in `finally`, thread reused | Create isolated context and clear on every exit path |
| 401 despite valid key | Wrong key format, env var not passed to process, mismatched hash, key revoked/expired | Check secret store config and metadata without logging raw keys |
| Two key headers accepted unpredictably | Proxy/container merges or picks first/last header differently | Reject duplicate/malformed headers, normalize at gateway |
| Expired API key still works | Stale cache, session/sticky auth, or revoked state not checked | Review cache invalidation, expiry, and stateless auth |
| Admin rights revoked yet requests still pass | Role read from key header or stale authorities cache | Read strictly from trusted server-side policy with refresh mechanism |
| Filter runs twice | Filter is an auto-registered Spring `@Bean` and also added to SecurityFilterChain | Instantiate filter locally inside chain or intentionally disable auto-registration |
| Key header appears in access logs | Reverse proxy/APM logs all request headers | Redact key before logging/export and immediately rotate exposed key |
| `ProviderNotFoundException` | Manager has no provider for the token type; `supports()` returns false | Check manager, token class, and registration |
| Adding POST returns 403 despite valid key | CSRF rule or authorization rule still applies | Distinguish CSRF vs missing authorities; adjust proper chain/matcher |
| MockMvc passes but production returns 401 | Secret store out of sync, gateway strips header, traffic hits another chain | Test through ingress/TLS and verify deployed versions/configs |

Diagnostic sequence: did the request hit the right chain → did the filter read a unique key → which provider did the manager use → did the provider verify the key store and status → what principal/authorities does Authentication have → which authorization rule applied. Only log key ID/client ID, trace ID, and generic error codes; **never log raw secrets or digests that could be abused in an attack**.

## 13. Exercises and self-check questions

1. **Why shouldn't the filter set principal "admin" when seeing header `X-Role: ADMIN`?** Because that header is client-supplied data; authorities must be determined by the provider/server after verifying the credential.
2. **When a key is wrong, should the provider return `null` or throw an error?** For a token type the provider actually handles, an invalid key should throw `AuthenticationException`; `null` is for cases where the provider cannot decide and lets another suitable provider try.
3. **Difference between 401 and 403?** 401: no valid authentication; 403: valid authentication but insufficient permission for the resource.
4. **Does a provider that verified a key need to place the raw key into the authenticated Authentication?** No; keep only safe principal/authorities/metadata. Raw secrets must be erased from context as early as possible.
5. **Why choose `ProviderManager(provider)`?** To separate authentication coordination from specific verification logic using Spring Security's standard contract.
6. **When is writing a manager directly appropriate?** When an independent chain has specialized verification logic that needs no provider chain, yet still obeys the `authenticate(...)` contract and fail-closed behavior.
7. **Can `API_ADMIN` be treated as a default OAuth2 scope?** It is a custom application authority; OAuth scopes typically follow different conventions. Never automatically conflate the two permission systems.
8. **If revoked-key caching lasts 15 minutes, is revocation immediate?** No. TTL/invalidation must be designed to match the security SLA.
9. **Do API keys replace mTLS/OAuth2 for all systems?** No. Bearer API keys are simple but not cryptographically bound to the request; the choice depends on the threat model.
10. **Why is a test using `@WithMockUser` insufficient?** It mocks an already-existing Authentication; it does not test whether the filter/provider actually verifies the raw key.

**Extended practice exercise:** add an `api_key` table with `expires_at` and `revoked_at`; test that revoked or expired keys always receive 401, active keys lacking `API_ADMIN` receive 403, and rotation to key B enables zero-downtime transition. Separate `keyId` from secret, store digest/HMAC, and use test data; never commit real keys.

## 14. Official documentation

- Spring Security – Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Architecture / Adding a custom filter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- API `AuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- API `ProviderManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- API `AbstractAuthenticationToken`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- API `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security – SecurityContextHolder and SecurityContext: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder
- OWASP – REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Spring Boot 3.5.16 release note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
