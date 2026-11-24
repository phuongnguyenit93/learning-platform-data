# Never Accept Authorities or Authenticated State Directly from the Client

> **Topic:** Custom Providers — Spring Security Authentication (Servlet). The example uses **Java 17+, Spring Boot 3.3.5, and Spring Security 6.x**. The focus is the trust boundary when implementing `AuthenticationProvider`: credentials sent by the client are **unauthenticated data**; verified identity, `GrantedAuthority`, and `isAuthenticated()` must originate from trusted server-side processing.

## 1. Trust Boundary: Clients May Send Evidence, Never Grant Themselves Permissions

An HTTP request can carry any client-controlled data: JSON bodies, query parameters, arbitrary cookies, headers, including fields named `role`, `authorities`, `isAuthenticated`, or `authenticated`. An attacker can also bypass the frontend UI and craft requests directly with `curl`.

Example of an **untrusted** request:

```http
GET /api/admin?role=ADMIN&authenticated=true HTTP/1.1
Host: localhost:8080
X-Api-Key: wrong-key
X-Role: ROLE_ADMIN
X-Authenticated: true
```

Or a JSON body that an attacker can craft themselves:

```json
{
  "apiKey": "wrong-key",
  "username": "administrator",
  "authenticated": true,
  "roles": ["ROLE_ADMIN"],
  "authorities": ["accounts:write"]
}
```

The fields above are **not proof** that the sender is administrator. `authenticated: true` is just a boolean asserted by the sender. `ROLE_ADMIN` is also just a string asserted by the sender. If code copies them into `Authentication` and lets Spring Security process it, the application faces a **privilege escalation** vulnerability.

Boundaries to maintain:

- **Clients only present credentials or evidence to verify**: password, API key, OAuth2 access token, request signature, one-time code, etc.
- **The server verifies the evidence**: via `AuthenticationManager`, `AuthenticationProvider`, `PasswordEncoder`, signature/token verification services, or trusted data sources.
- **The server determines identity and permissions**: retrieves user/roles from a verified source; never accepts an arbitrary list of permissions sent alongside credentials.
- **The authentication mechanism places the trusted result into `SecurityContext`**: this result is the token returned by the provider after verification, not the raw token built from the request.

**Remember:** an unverified username, email, userId, or claim is still just raw data. It does not become trustworthy merely because a field name resembles an internal Spring Security concept.

## 2. Understanding `Authentication` and `isAuthenticated()` Properly

`Authentication` serves two distinct stages:

| Stage | `principal` | `credentials` | `authorities` | `isAuthenticated()` |
| --- | --- | --- | --- | --- |
| **Inbound request**, created from client data | May be an unverified username/key ID, or null | Raw credentials needing verification | Never taken from client; usually empty | `false` |
| **Successful result** returned by manager/provider | Identity verified by the server | Should omit/mask/erase raw credentials | Authorities determined by the server | `true` |
| **Failure** | No trusted result produced | Never logged or returned in response | No authorities granted | Throws `AuthenticationException` |

For username/password, an illustrative snippet inside a handler method:

```java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                usernameFromRequest,
                rawPasswordFromRequest
        );

Authentication verified = authenticationManager.authenticate(requestToken);
```

This is an **illustrative snippet**, not a standalone program. The `unauthenticated` factory creates an untrusted request. `AuthenticationManager.authenticate(...)` returns a verified `Authentication` or throws `AuthenticationException`. It **does not return a boolean** for code to decide on its own to raise privileges.

**Dangerous anti-pattern:**

```java
// Wrong: identity/authorities/state all come from the client.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
        request.username(),
        null,
        request.roles().stream()
                .map(SimpleGrantedAuthority::new)
                .toList()
);
SecurityContextHolder.getContext().setAuthentication(forged);
```

This snippet also illustrates a design flaw; `request` merely represents client-supplied data. With this approach, an attacker submits `ROLE_ADMIN` and the application recognizes that role on its own. Likewise, never directly call `SecurityContextHolder.getContext().setAuthentication(authenticationFromJson)` or let Spring MVC/Jackson deserialize a trusted `Authentication` object straight from JSON.

### Why Is `setAuthenticated(true)` Especially Sensitive?

Under the `Authentication` contract, `isAuthenticated()==true` can cause security layers to treat the token as having passed authentication. It is an **assertion of trusted state**. A custom `Authentication` must never allow arbitrary request-handling code to call `setAuthenticated(true)` with unverified data.

A safe design for a custom token normally includes:
1. A factory/constructor creating a **request token** with `isAuthenticated=false` and no client-asserted authorities.
2. A factory/constructor creating a **verified token** called only after the provider verifies credentials.
3. Overriding `setAuthenticated(true)` to throw `IllegalArgumentException`, preventing direct state flipping.
4. Allowing `setAuthenticated(false)` per Spring Security's contract; never storing raw credentials in the verified token.
5. Providing no setters for principal/authorities once authenticated.

This is why you should use controlled factories like `UsernamePasswordAuthenticationToken.unauthenticated(...)` and `authenticated(...)` rather than passing a client-manipulable token directly into the context.

## 3. Role of a Custom `AuthenticationProvider`

A custom provider is used when the application's credential mechanism is not supported out of the box, such as an internal API key, request signature, or custom auth code. The provider must answer: **is this credential valid, which identity does it belong to, and what permissions does it have per server policy?**

Expected flow:

```text
Untrusted HTTP request
  |
  | X-Api-Key: <raw credential>
  | X-Role: ROLE_ADMIN       (ignored)
  | X-Authenticated: true    (ignored)
  v
API-key authentication filter
  |
  |-- Creates ApiKeyAuthenticationToken.unauthenticated(key)
  v
AuthenticationManager.authenticate(...)
  |
  v
ProviderManager
  |
  |-- Selects provider where supports(ApiKeyAuthenticationToken.class) is true
  v
ApiKeyAuthenticationProvider
  |
  |-- Verifies credential against server-side trusted source
  |-- Checks account validity, tenant, and policies if needed
  |-- Determines username + GrantedAuthority FROM SERVER
  |-- Invalid -> BadCredentialsException
  |-- Valid -> creates verified token, credentials=null, authenticated=true
  v
Filter creates a new SecurityContext and sets verified token
  |
  v
AuthorizationFilter
  |-- /api/whoami requires authenticated() -> allowed
  |-- /api/admin requires ROLE_ADMIN -> 403 if server only granted ROLE_READER
```

The two methods of `AuthenticationProvider`:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

- `supports` returns `true` when the provider knows how to handle this **type** of token. It does not assert that credentials are valid.
- `authenticate` must **verify** credentials before returning an authenticated token. It can return `null` if it cannot decide and wants another provider tried; when **credentials have been evaluated and are invalid**, it should throw an appropriate `AuthenticationException` (e.g., `BadCredentialsException`) rather than accepting by default.
- `ProviderManager` coordinates providers; avoid an overly broad provider accidentally accepting tokens from another mechanism.
- Account permissions may be roles, scopes, permissions, or tenant-scoped mappings; all must come from server data checked at the appropriate time. If genuine delegated authorization exists, you must verify signature, issuer, audience, expiry, and delegation scope before using claims.

## 4. Runnable Example: Custom API-Key Provider with Server-Granted Authorities

To see the trust boundary clearly, the example uses an **API key sent explicitly via header** `X-Api-Key`. This is a stateless authentication mechanism: every request must present the key itself, without relying on cookies/sessions. The demo only accepts key `demo-reader-key-123` and maps it server-side to principal `service-reader` with **only** `ROLE_READER`.

A client trying to send `X-Role: ROLE_ADMIN` or `X-Authenticated: true` will not change the outcome. Using a hardcoded key here is **strictly for learning**. In production you need high-entropy keys, issuance and hash/secret storage via a secret vault, rotation/revocation, TLS, rate limiting, auditing, and abuse monitoring.

### 4.1. Project Structure

```text
api-key-trust-demo/
├── pom.xml
├── src/main/java/com/example/apikey/ApiKeyTrustDemoApplication.java
└── src/test/java/com/example/apikey/ApiKeyTrustDemoApplicationTests.java
```

**`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>api-key-trust-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <groupId>org.springframework.boot</groupId>
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

**`src/main/java/com/example/apikey/ApiKeyTrustDemoApplication.java`**:

```java
package com.example.apikey;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.List;

@SpringBootApplication
public class ApiKeyTrustDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiKeyTrustDemoApplication.class, args);
    }

    @Bean
    AuthenticationManager authenticationManager() {
        return new ProviderManager(List.of(new DemoApiKeyProvider()));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/whoami").authenticated()
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .csrf(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
                )
            )
            // Add this filter only to the Spring Security chain, no @Component.
            .addFilterBefore(
                new ApiKeyFilter(authenticationManager),
                UsernamePasswordAuthenticationFilter.class
            );

        return http.build();
    }

    // Inbound token and authenticated token have separate constructors.
    static final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {
        private final Object principal;
        private String apiKey;

        private ApiKeyAuthenticationToken(String rawKey) {
            super(List.of());
            this.principal = null;
            this.apiKey = rawKey;
            super.setAuthenticated(false);
        }

        private ApiKeyAuthenticationToken(
                String verifiedPrincipal,
                Collection<? extends GrantedAuthority> authorities) {
            super(authorities);
            this.principal = verifiedPrincipal;
            this.apiKey = null;
            // Only this constructor is allowed to set the trusted state.
            super.setAuthenticated(true);
        }

        static ApiKeyAuthenticationToken unauthenticated(String rawKey) {
            return new ApiKeyAuthenticationToken(rawKey);
        }

        static ApiKeyAuthenticationToken verified(
                String serverPrincipal,
                Collection<? extends GrantedAuthority> serverAuthorities) {
            return new ApiKeyAuthenticationToken(serverPrincipal, serverAuthorities);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return apiKey;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            apiKey = null;
        }

        @Override
        public void setAuthenticated(boolean value) {
            if (value) {
                throw new IllegalArgumentException(
                        "Cannot trust token via setAuthenticated(true)"
                );
            }
            super.setAuthenticated(false);
        }
    }

    static final class DemoApiKeyProvider implements AuthenticationProvider {
        private static final byte[] EXPECTED_HASH = sha256("demo-reader-key-123");

        @Override
        public Authentication authenticate(Authentication authentication) {
            String presented = (String) authentication.getCredentials();
            if (presented == null || presented.isBlank()
                    || !MessageDigest.isEqual(sha256(presented), EXPECTED_HASH)) {
                throw new BadCredentialsException("Invalid API key");
            }

            // IMPORTANT: username + authority come from the server side.
            return ApiKeyAuthenticationToken.verified(
                    "service-reader",
                    List.of(new SimpleGrantedAuthority("ROLE_READER"))
            );
        }

        @Override
        public boolean supports(Class<?> authentication) {
            return ApiKeyAuthenticationToken.class.isAssignableFrom(authentication);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException("SHA-256 unavailable", ex);
            }
        }
    }

    static final class ApiKeyFilter extends OncePerRequestFilter {
        private final AuthenticationManager authenticationManager;

        ApiKeyFilter(AuthenticationManager authenticationManager) {
            this.authenticationManager = authenticationManager;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {

            String rawKey = request.getHeader("X-Api-Key");
            if (rawKey == null || rawKey.isBlank()) {
                chain.doFilter(request, response);
                return;
            }

            try {
                Authentication pending =
                        ApiKeyAuthenticationToken.unauthenticated(rawKey);
                Authentication verified =
                        authenticationManager.authenticate(pending);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
                chain.doFilter(request, response);
            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            }
        }
    }

    @RestController
    static class DemoController {
        record IdentityResponse(
                String username,
                boolean authenticated,
                List<String> authorities
        ) {}

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/whoami")
        IdentityResponse whoAmI(Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new IdentityResponse(
                    authentication.getName(),
                    authentication.isAuthenticated(),
                    authorities
            );
        }

        @GetMapping("/api/admin")
        String adminOnly() {
            return "admin-only";
        }
    }
}
```

### 4.2. Why Does This Design Not Trust Client Authorities?

**One:** `ApiKeyFilter` only reads `X-Api-Key`. It does not read `X-Role`, `X-Authenticated`, `role`, or `authenticated` from query parameters. Client-asserted fields can never become a `GrantedAuthority`.

**Two:** The filter creates `ApiKeyAuthenticationToken.unauthenticated(rawKey)`, where `isAuthenticated=false`, principal = `null`, and authorities are empty. It passes the token through `AuthenticationManager.authenticate(...)`; it never calls `setAuthenticated(true)`.

**Three:** `DemoApiKeyProvider` compares the hash of the client-presented key against the trusted hash configured on the server. Only when the key matches does the provider create a verified token with principal `service-reader` and **server-sourced ROLE_READER**, ignoring roles from the request. Using a SHA-256 hash on a low-entropy demo key is **not a production API key store design**: in reality you must issue long random keys, with a key ID, proper hash/HMAC store, rotation, and revocation.

**Four:** `ApiKeyAuthenticationToken#setAuthenticated(true)` is blocked. The verified constructor may call `super.setAuthenticated(true)` after verification; the token class itself only exposes an unauthenticated request creation path to the filter. If another developer tries to elevate the request token via the setter, the code throws an exception.

**Five:** `getAuthorities()` of the verified token is the collection passed by the server into the constructor and guarded by `AbstractAuthenticationToken` per contract. Never expose mutable setters for authorities or return a collection that can be modified after authentication.

**Six:** The filter only puts the **`verified` result** into `SecurityContextHolder`. It never copies `pending` or request headers into an authenticated token. `AuthorizationFilter` inspects `ROLE_READER` and denies `/api/admin` because that endpoint requires `ROLE_ADMIN`.

**Seven:** The example is stateless: `NullSecurityContextRepository` and `SessionCreationPolicy.STATELESS` mean the context is not used to establish long-lived login. Every request must carry valid credentials. CSRF is disabled **within the scope of a header-only demo not using automatically sent cookies**; do not apply this unconditionally to web logins using sessions/cookies.

**Eight:** The filter is instantiated directly in `addFilterBefore` instead of being declared as a servlet `@Component`/`@Bean Filter`, avoiding Spring Boot auto-registering a filter outside `SecurityFilterChain` and registering it a second time inside the chain.

### 4.3. Running and Testing with curl

From the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
# Public endpoint requires no credentials.
curl -i http://localhost:8080/public

# No key -> 401 on protected endpoint.
curl -i http://localhost:8080/api/whoami

# Wrong key, even when claiming to be admin -> 401.
curl -i \
    -H 'X-Api-Key: wrong-key' \
    -H 'X-Role: ROLE_ADMIN' \
    -H 'X-Authenticated: true' \
    'http://localhost:8080/api/admin?role=ADMIN&authenticated=true'

# Valid key -> 200, receives only server-assigned ROLE_READER.
curl -i \
    -H 'X-Api-Key: demo-reader-key-123' \
    -H 'X-Role: ROLE_ADMIN' \
    -H 'X-Authenticated: true' \
    http://localhost:8080/api/whoami

# Same valid key without ROLE_ADMIN -> 403.
curl -i \
    -H 'X-Api-Key: demo-reader-key-123' \
    -H 'X-Role: ROLE_ADMIN' \
    'http://localhost:8080/api/admin?role=ADMIN'
```

Expected results in order: **200**, **401**, **401**, **200**, **403**. The body of `GET /public` is the string `public`. The JSON body of `/api/whoami` reflects the server-issued identity; illustration:

```json
{
  "username": "service-reader",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

Field/header ordering and error bodies may vary depending on Spring Boot/Servlet container configuration; the JSON example above describes values rather than exact byte order. The `authenticated: true` line in the **response** is a server-verified state, completely different from a client-asserted boolean.

## 5. Tests Against Forged Roles and Authenticated State

Create **`src/test/java/com/example/apikey/ApiKeyTrustDemoApplicationTests.java`**:

```java
package com.example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyTrustDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void validKeyProducesOnlyServerAssignedIdentityAndRole() throws Exception {
        mvc.perform(get("/api/whoami")
                    .header("X-Api-Key", "demo-reader-key-123")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true")
                    .param("role", "ADMIN")
                    .param("authenticated", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("service-reader"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"));
    }

    @Test
    void forgedRoleDoesNotBypassAuthorization() throws Exception {
        mvc.perform(get("/api/admin")
                    .header("X-Api-Key", "demo-reader-key-123")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true")
                    .param("role", "ADMIN"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidOrMissingKeyCannotBeAuthenticatedByHeaders() throws Exception {
        mvc.perform(get("/api/whoami")
                    .header("X-Api-Key", "wrong-key")
                    .header("X-Role", "ROLE_ADMIN")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/whoami")
                    .header("X-Authenticated", "true"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void inputTokenCannotBePromotedBySetter() {
        var token = ApiKeyTrustDemoApplication.ApiKeyAuthenticationToken
                .unauthenticated("wrong-key");

        assertFalse(token.isAuthenticated());
        assertThrows(IllegalArgumentException.class,
                () -> token.setAuthenticated(true));
        assertFalse(token.isAuthenticated());
    }
}
```

Run:

```bash
mvn test
```

The tests verify behaviorally:
1. Valid credentials with headers/queries claiming admin do not alter the server-side principal/authority.
2. Valid credentials with **insufficient role** return 403.
3. Invalid or missing credentials cannot be turned into a login via `X-Authenticated: true`, returning 401.
4. An unauthenticated request token cannot be turned into a trusted token via `setAuthenticated(true)`.
5. Public endpoint still works, confirming the application runs through the filter chain.

`MockMvc` runs the Spring Security filter chain and controller in tests without opening a real HTTP port.

## 6. Other Pitfalls in Custom Providers

### 6.1. Authorities Must Be Determined from Trusted Evidence

A user might send `userId=42` or `tenant=acme`, yet the provider must prove the key/token belongs to that exact user and tenant before querying authorities. **Do not use `request.userId` or `request.tenantId` as the authentication result** if they are merely client-entered strings. In multi-tenant apps, identity and roles are usually identified by an account/tenant pair and server policy; trust a tenant selector only after verifying its binding with the credential.

If an external identity provider sends a JWT, you must verify signature, allowed algorithms, issuer, audience, `exp`/`nbf` timestamps, and token context before using `scope`/`roles`. Simply Base64-decoding a JWT and reading JSON claims is **not authentication**.

### 6.2. Do Not Create an Authenticated Token Before the Provider Verifies

**Wrong:**

```java
// Wrong: client sends authorities, code immediately treats them as trusted.
Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
                input.username(), null,
                input.roles().stream().map(SimpleGrantedAuthority::new).toList()
        );
SecurityContextHolder.getContext().setAuthentication(authentication);
```

**Correct in terms of responsibility:**

```java
// Illustrates flow only; variables belong to external real code.
Authentication pending = ApiKeyAuthenticationToken.unauthenticated(rawKey);
Authentication verified = authenticationManager.authenticate(pending);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
```

These two snippets are illustrations, not standalone Java files. The complete actual code is in section 4; `verified` is created by the provider **only after** verifying credentials and assigning authorities from the server.

### 6.3. Distinguishing 401 and 403

| Scenario | Deciding component | Typical result |
| --- | --- | --- |
| No credentials, URL requires authentication | Authorization + authentication entry point | **401 Unauthorized** |
| Wrong credentials, provider throws `BadCredentialsException` | Authentication filter/entry point | **401 Unauthorized** |
| Valid credentials, user only has `ROLE_READER` but URL requires `ROLE_ADMIN` | `AuthorizationFilter`/`AccessDeniedHandler` | **403 Forbidden** |
| `X-Role` header spoofing admin role | No effect | Follows **server-verified** credentials/roles |
| Boolean `authenticated=true` in JSON/query/header | No effect | Follows **server-verified** credentials |

`401` does not mean missing role; `403` does not mean wrong password/API key. Responses may vary if an application configures custom entry points/handlers, but distinguishing authentication from authorization remains vital.

### 6.4. Never Store Raw Credentials or Leak Sensitive Data

- API keys/passwords are secrets. Never write raw keys into logs, exceptions, `toString`, response bodies, or metrics tags.
- The verified token in the example has `getCredentials()==null`; the provider holds the raw key only for the duration needed to verify it.
- For long-lived credentials, use high-entropy keys, store an appropriate hash/HMAC, bind owner/scope/expiry/revocation, and compare safely; the demo fixed key is insufficient.
- Use HTTPS/TLS, control access logs/traces, configure secret rotation, and limit attempt counts.
- Never store a client-sent JSON `Authentication` in session/cache. Only the server creates trusted results.

### 6.5. Do Not Use `isAuthenticated()` Alone to Infer Permissions

`Authentication.isAuthenticated()` returns authentication state; it **does not say the user has admin rights**. `authorizeHttpRequests(...hasRole("ADMIN"))` checks authorities from the verified token. When a custom provider assigns `ROLE_ADMIN` to every valid token, the bug is in **server** authority mapping even if the client sent no role. Therefore you must also audit the identity → permissions mapping.

In mechanisms using `AnonymousAuthenticationToken`, `isAuthenticated()` can be true in certain contexts. To check whether someone is logged in, use the `authenticated()` expression and `AuthenticationTrustResolver` semantics rather than writing `if (authentication.isAuthenticated())` as a sole authorization check.

### 6.6. Provider Supports the Exact Token Type

`supports(ApiKeyAuthenticationToken.class)` must return true, yet it should not support every token in the system. If multiple providers are registered with the same manager, a provider must return the exact supported token type; if credentials are wrong, throw an appropriate exception. `ProviderManager` can move to the next provider depending on exception types/configuration, so provider ordering and fallback design must never accidentally allow a weaker mechanism to elevate privileges.

### 6.7. Why Does the Demo Not Use Sessions?

For clarity of observation, the API key is sent on every request: the filter re-verifies and sets the context only for the current request; `SecurityContextHolderFilter` cleans up the context after the request. `NullSecurityContextRepository` does not retain context between requests. If switching to session login, choose an appropriate repository, persist context after success via `saveContext(...)`, and handle session fixation and CSRF. If using a JWT Resource Server, prefer the built-in mechanism to verify signatures/claims rather than writing a provider that merely reads client-asserted JSON claims.

## 7. Checklist When Reviewing Custom Authentication Code

- [ ] Inbound DTOs contain only necessary credentials/evidence, never accepting `authenticated`/`authorities` as trusted permissions.
- [ ] Every token created from a request starts with `isAuthenticated=false` and empty authorities.
- [ ] Manager/provider verifies credentials against a trusted source or valid signature before creating a verified token.
- [ ] Resulting `principal` and `GrantedAuthority` are determined by the server according to verified identity/tenant/policy.
- [ ] Custom token blocks arbitrary `setAuthenticated(true)` and exposes no mutable setters for authorities.
- [ ] Verified token holds no raw credentials; credentials are never leaked in responses/logs.
- [ ] Filter puts the **result** returned by the manager into `SecurityContext`, handles exceptions, and clears context on failure.
- [ ] `supports` accepts only the exact token type; no weak fallback accidentally elevates privileges.
- [ ] Tests cover forged `ROLE_ADMIN`, `authenticated=true`, invalid credentials, missing credentials, and insufficient permissions.
- [ ] TLS, secret rotation, tenant isolation, rate limiting, and auditing match risk levels.

## 8. Self-Check Knowledge

1. Why must `"ROLE_ADMIN"` in JSON/headers never be converted directly into a `SimpleGrantedAuthority`?
2. When a client sends `authenticated=true` with a wrong key, what is the state of `ApiKeyAuthenticationToken.unauthenticated`?
3. Which component verifies the key and which component grants `ROLE_READER` in the demo?
4. Why does the same valid key return 200 on `/api/whoami` yet 403 on `/api/admin`?
5. In the verified token constructor, why is `super.setAuthenticated(true)` used only after the provider has verified credentials?
6. If a JWT has an unverified signature, why must `roles` in its payload never be used for authorization?
7. Why does `isAuthenticated()` alone not replace `hasRole(...)` and `AuthenticationTrustResolver`?
8. When replacing the demo with production API keys, what additional measures are needed for secrets, expiry, and tenant-scoped permissions?

**Core answers:** (1) clients can self-assert them; (2) false, manager/provider must verify; (3) `DemoApiKeyProvider`, based on server data; (4) server only grants `ROLE_READER`; (5) true is the authenticated signal; (6) payload is untrusted; (7) authentication differs from authorization and anonymous has special rules; (8) strong random keys, hash/secret store, expiry, rotation/revocation, server-side permissions, TLS, and tenant checks.

## 9. Official Documentation

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — `Authentication` interface API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html
- Spring Security — `AuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security — `AbstractAuthenticationToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html
- Spring Security — Authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — SecurityContext persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
