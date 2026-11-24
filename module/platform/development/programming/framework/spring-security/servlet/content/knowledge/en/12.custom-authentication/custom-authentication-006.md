# Crafting Success and Failure Responses Suitable for REST APIs in Custom Authentication

## 1. Goal: Authentication Is Business Logic, HTTP Response Is the API Contract

A REST API is typically called by web frontends, mobile apps, or other services. These clients expect **HTTP status codes**, **JSON responses**, and **authentication details** following an explicit contract, rather than being redirected to an HTML login page.

When writing a custom authentication endpoint, the application must answer five questions distinctly:

1. **Is the request well-formed?** Valid JSON, required fields, appropriate content type.
2. **Are the credentials accepted?** Username/password, API key, token, or chosen mechanism.
3. **Authenticated, yet authorized for the resource?** This is authorization, separate from authentication.
4. **On success, how does the client use the result?** Receive user info, an access token, or a cookie/session per the actual design.
5. **On failure, how does the client recover?** Read a stable error code without leaking sensitive information.

In **Spring Security Servlet**, API success/failure responses can be handled in a controller, inside an authentication filter's `AuthenticationSuccessHandler` / `AuthenticationFailureHandler`, via `AuthenticationEntryPoint` for unauthenticated callers, or via `AccessDeniedHandler` when authenticated yet lacking permissions.

**Key principle:** Do not confuse these handling points. A tidy JSON response does not make a custom authentication flow secure if you bypass `AuthenticationManager`, store tokens improperly, or leak account state.

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, and the Servlet stack**. The runnable example in section 7 simulates a **stateless API using random Bearer tokens**: `POST /api/auth/login` returns a JSON token on success; subsequent requests send `Authorization: Bearer <token>`; 400/401/403 responses are also JSON. The demo token is stored in memory with a short lifetime, and is **not a production token service**.

## 2. Choosing HTTP Status Codes by Practical Meaning

| Scenario | Typical Status | Meaning in the API |
| --- | --- | --- |
| Valid login request, authentication succeeds and issues token | **200 OK** | Client receives JSON containing token and expiration |
| Login succeeds and no response body is needed | **204 No Content** | Appropriate when authentication result is managed via another mechanism and no body is needed |
| Malformed JSON body, missing required parameter, or invalid schema | **400 Bad Request** | Request input violates the contract |
| Wrong username/password, account disallowed from authenticating, missing/expired/invalid Bearer token | **401 Unauthorized** | Request is not validly authenticated for this operation |
| Validly authenticated but insufficient role/permission | **403 Forbidden** | Valid identity exists, but action is not permitted |
| Non-existent API path | **404 Not Found** | Resource not found; auth policy may deny before request reaches MVC |
| Too many login attempts or rate limit exceeded | **429 Too Many Requests** | Requires rate limiting policy and optionally `Retry-After` |
| Infrastructure/identity provider unavailable | Appropriate **5xx** | Never disguise every system outage as "wrong password" |

Two common confusions:

- **401 does not mean "missing ROLE_ADMIN".** That is usually 403 *after* a valid identity has been authenticated. If a custom entry point or resource-hiding policy exists, results may differ; define a consistent contract.
- **403 is not the default for wrong password.** A `POST /login` request missing a CSRF token can be rejected with 403 **before** password checking, yet that is a CSRF failure, not a conclusion about the account.

Whether 200 or 201 is used depends on the contract and created resource. In the bearer-token issuance example, we use **200** with a body containing token details; do not pick 201 merely because the request is POST.

## 3. Designing Stable JSON Responses

### 3.1. Login Success

An illustrative contract:

~~~json
{
  "tokenType": "Bearer",
  "accessToken": "<opaque-random-token>",
  "expiresIn": 900
}
~~~

`accessToken` in the example is only an **illustrative placeholder**, not a real token. `expiresIn` is measured in **seconds**. The API includes `Cache-Control: no-store` to reduce the chance of responses containing tokens being cached unintentionally.

Never return passwords, password hashes, secret keys, the full `Authentication` object, or unnecessary internal data. Return only what the client needs to call the API.

If the application uses session cookies instead of tokens, the success response may return only user/profile details; cookies must be configured with appropriate `Secure`, `HttpOnly`, and `SameSite` flags, and the flow must address CSRF. **Never combine the two models without understanding how browsers automatically attach credentials.**

### 3.2. Credential Failure

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Invalid login credentials."
}
~~~

This 401 response can be shared **uniformly** for non-existent usernames, wrong passwords, or locked, disabled, expired, or credentials-expired accounts on public login screens. Never return responses such as:

~~~json
{
  "code": "USER_EXISTS_BUT_LOCKED",
  "message": "Account alice is currently locked"
}
~~~

The second snippet is an **anti-pattern**: unauthenticated attackers can use it to enumerate usernames and account statuses.

Public error codes should guide **the client's next action**, not expose full internal exception structures. The system can still audit the underlying reason in a protected location under proper data policies.

### 3.3. Schema Failure

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "Invalid request."
}
~~~

A **400** response can be used for malformed JSON, structurally invalid username/password fields, or a missing body. Never return 200 with `"success": false` just to avoid handling HTTP status codes: that makes it hard for clients, proxies, monitoring, and retry logic to distinguish valid from failed requests.

### 3.4. Logged In but Lacking Permission

~~~json
{
  "code": "FORBIDDEN",
  "message": "You do not have permission to access this resource."
}
~~~

A **403** response must not expose internal authorization rules or other resources' data. For example, a user logged in with `ROLE_USER` requesting `GET /api/admin` restricted to `ROLE_ADMIN`.

### 3.5. Suggested Error Contract

| Field | Meaning | Notes |
| --- | --- | --- |
| `code` | Stable, machine-readable error code | Clients branch on code, not by parsing message text |
| `message` | Safe, readable message | Can be localized; must not contain stack traces/secrets/account state |
| `requestId` | Correlation ID for ops support (if supported) | Generated by infrastructure; never use tokens or session IDs as requestId |
| `details` | Non-sensitive validation error list (optional) | Exclude user tables, exception classes, SQL, or security internals |
| HTTP status | Transport-level meaning | Never use `200` for all errors; reflect 400/401/403/429/5xx accurately |

Stay consistent on content type `application/json` or `application/problem+json`. A project may choose **RFC 9457 Problem Details** with Spring's `ProblemDetail`, or a custom `code/message` schema like this example; there is no need to mix both on the same endpoint. What matters is documenting the schema and testing it.

## 4. Key Extension Points in Spring Security

### 4.1. AuthenticationManager and AuthenticationProvider

Credential verification should be handled by a trusted `AuthenticationManager`/`AuthenticationProvider`, never by creating an authenticated token solely from a client-supplied username:

~~~java
Authentication result = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);
~~~

This is an **integration snippet**. `authenticationManager`, `username`, and `rawPassword` come from the login component after input validation. `result` is considered authenticated only when the provider accepts the credentials. For `UserDetails`-based providers, account states such as locked/disabled/expired can also cause authentication to fail.

**Dangerous mistake:**

~~~java
// DO NOT use: client self-declares user/role and server marks it authenticated.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

The snippet above illustrates **unauthorized self-elevation** if identity and roles come directly from the client. Constructors/methods creating authenticated tokens are used only after a trusted verification step accepts the credentials.

### 4.2. AuthenticationSuccessHandler

`AuthenticationSuccessHandler` belongs to an authentication flow managed by a security filter (such as a custom `AuthenticationFilter` or a subclass of `AbstractAuthenticationProcessingFilter`). It determines **the response when the filter authenticates successfully**.

Illustrative JSON example:

~~~java
AuthenticationSuccessHandler success = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write("{\"status\":\"AUTHENTICATED\"}");
};
~~~

This is a **snippet**, requiring the relevant Java/Spring Security imports. The response above only confirms success; **it does not issue a token or save a session by itself**. If this is a login endpoint for clients needing persistent authentication, the handler or service layer must invoke a valid session/token mechanism. You cannot assume subsequent requests are logged in merely because HTTP 200 was returned.

### 4.3. AuthenticationFailureHandler

`AuthenticationFailureHandler` handles **authentication failures inside a filter**:

~~~java
AuthenticationFailureHandler failure = (request, response, exception) -> {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
        "{\"code\":\"AUTHENTICATION_FAILED\",\"message\":\"Invalid login credentials.\"}"
    );
};
~~~

Never return `exception.getMessage()` directly to clients. `BadCredentialsException`, `LockedException`, `DisabledException`, and `CredentialsExpiredException` are technical details suitable for internal auditing, not public responses.

If you authenticate inside a **REST controller** instead of a security filter, `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` are **not invoked automatically**. The controller can return `ResponseEntity` adhering to the same contract, as in the full example in section 7.

### 4.4. AuthenticationEntryPoint

`AuthenticationEntryPoint` handles requests to resources requiring authentication when **no valid authentication exists yet**. For REST APIs, it typically returns JSON **401** instead of a `302` redirect to form login.

Example request:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
~~~

And response:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Bearer
Cache-Control: no-store

{"code":"UNAUTHORIZED","message":"Valid authentication is required."}
~~~

`WWW-Authenticate: Bearer` is the standard challenge for resources requiring a Bearer token. Do not blindly attach a Bearer challenge to APIs using only sessions or mTLS. In the standard Bearer scheme, detailed error parameters follow specific rules; the demo uses only the general header.

### 4.5. AccessDeniedHandler

`AccessDeniedHandler` handles **authorization failures** when an authenticated principal lacks permission. Responses for REST APIs are typically JSON **403**; do not redirect to an HTML login page. If an anonymous request triggers `AccessDeniedException`, `ExceptionTranslationFilter` may delegate to `AuthenticationEntryPoint` to return 401—so not every `AccessDeniedException` results in 403.

### Table for Choosing the Right Handler

| Case | Usually Appropriate Extension Point |
| --- | --- |
| Custom authentication filter succeeds | `AuthenticationSuccessHandler` |
| Custom authentication filter fails | `AuthenticationFailureHandler` |
| REST controller calls `AuthenticationManager.authenticate` itself | `ResponseEntity` + controlled `AuthenticationException` handling |
| GET protected resource missing bearer token | `AuthenticationEntryPoint` |
| GET resource already authenticated but lacking role | `AccessDeniedHandler` |
| Malformed JSON body | MVC exception handler / `@RestControllerAdvice` |
| Validation or business exception | Controller/advice/service mapping layer; not treated as authentication failure |

**Do not confuse form login's `failureUrl` with REST API responses.** `failureUrl` usually produces a `302` redirect to an HTML login page; API clients usually need consistent 401 JSON.

## 5. Stateless Bearer Token vs Session Cookie Are Two Distinct Choices

### 5.1. Demo in This Lesson: Per-Request Bearer Token

~~~text
POST /api/auth/login, JSON username/password
  |
  v
AuthenticationManager verifies credentials
  |
  +-- failure -> 401 generic JSON
  |
  +-- success -> generate random (opaque) token and TTL
                     |
                     v
                 200 JSON { tokenType, accessToken, expiresIn }
                     |
                     v
Client sends: Authorization: Bearer <token>
                     |
                     v
Bearer filter looks up token hash in token store
                     |
                     +-- invalid/expired -> 401 JSON
                     |
                     +-- valid -> attach Authentication to SecurityContext
                                      |
                                      v
                             authorization rule
                                      |
                                      +-- missing role -> 403 JSON
                                      +-- sufficient permission -> Controller -> 200 JSON
~~~

In this model, **cookies/sessions are not used as credentials**. A Bearer token is a secret: anyone possessing a valid token can act as that user. Therefore it must travel over HTTPS, avoid URLs, logs, or XSS-exposed local storage; clients need storage strategies suited to their platform. When a token expires, the client logs in again or uses a dedicated refresh flow.

The example uses a **random opaque token** and an in-memory store for clarity. It is not a JWT, cannot be verified offline by signature, does not survive restarts, and cannot be shared across multiple server instances. Production should use OAuth2/OIDC + Spring Security Resource Server or a token service with a store providing reliable TTL/revocation, rather than inventing a custom bearer scheme.

### 5.2. If Choosing Session Cookies

If the application returns a cookie after login and the browser sends it automatically on subsequent requests, you must manage sessions, `SameSite`/`Secure`/`HttpOnly`, CSRF, and session fixation. Disabling CSRF merely because an endpoint is called REST **is wrong**. The stateless demo can disable CSRF under the condition that **it uses no cookies/credentials automatically attached by browsers** for authentication. Adding cookies later requires re-evaluating CSRF.

### 5.3. JWT vs Opaque Token

JWTs typically contain claims and a signature verified with a key; never merely decode the payload and trust roles. Opaque tokens typically require token store lookup or introspection. Whichever you choose, verify expiry, issuer/audience/scope, revocation, current permissions, and key/state protection policies. **This example only illustrates REST response logic and a minimal development token mechanism**; it is not an OAuth2 deployment standard.

## 6. Concrete Contract of the Example REST API

| Request | Credentials | Expected Result |
| --- | --- | --- |
| `POST /api/auth/login` | Valid username/password | 200, JSON token |
| `POST /api/auth/login` | Wrong password, unknown username, locked | 401, generic `AUTHENTICATION_FAILED` code |
| `POST /api/auth/login` | Invalid JSON or missing field | 400, `INVALID_REQUEST` code |
| `GET /api/public` | None required | 200, public JSON |
| `GET /api/me` | Missing Bearer token | 401, `UNAUTHORIZED` code |
| `GET /api/me` | Fake/expired token | 401, `UNAUTHORIZED` code |
| `GET /api/me` | Valid token for alice | 200, username JSON |
| `GET /api/admin` | Valid token for alice (USER) | 403, `FORBIDDEN` code |
| `GET /api/admin` | Valid token for admin (ADMIN) | 200, admin-ok JSON |

401 responses for tokens on protected resources include `WWW-Authenticate: Bearer`. Codes and messages from login failures never confirm whether an account exists, is locked, or is expired.

## 7. Complete Example: Spring Boot 3, Security 6, Java 17, JSON + Opaque Bearer Token

This is an end-to-end **Spring Boot Maven project** working with HTTP JSON. It includes:

- `AuthenticationManager` backed by `DaoAuthenticationProvider` checking BCrypt passwords and `UserDetails` status.
- `POST /api/auth/login` accepting JSON, returning 200 token or 400/401 JSON.
- `TokenService` generating a 32-byte random token with `SecureRandom`, storing its **SHA-256 fingerprint** as the key in a `ConcurrentHashMap` with a 15-minute TTL. The raw token is returned only to the client.
- `BearerTokenFilter` verifying tokens on subsequent requests, creating a new `SecurityContext` per request, attaching `Authentication` only when the token is valid.
- `AuthenticationEntryPoint` for 401 JSON, `AccessDeniedHandler` for 403 JSON, `@RestControllerAdvice` for invalid JSON.
- `MockMvc` tests verifying login success, login failure, missing token, invalid token, and ADMIN permissions.

**Intentional limitations:** the in-memory token store is lost on restart, is not shared across replicas, does not evict expired tokens that are never accessed again, and has no refresh tokens, revocation, replay/device binding, rate limiting, per-request account-state rechecks, or OAuth2 interoperability. **Do not deploy as-is in production.** The goal is to clearly show response responsibilities and the authentication flow; in real deployments, prefer vetted token libraries/infrastructure.

### 7.1. Structure

~~~text
rest-auth-response/
├── pom.xml
└── src/
    ├── main/java/com/example/restauth/
    │   ├── RestAuthApplication.java
    │   ├── SecurityConfig.java
    │   ├── ApiError.java
    │   ├── ApiErrors.java
    │   ├── TokenService.java
    │   ├── BearerTokenFilter.java
    │   ├── ApiController.java
    │   └── ApiExceptionAdvice.java
    └── test/java/com/example/restauth/AuthApiTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rest-auth-response</artifactId>
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
~~~

**`src/main/java/com/example/restauth/RestAuthApplication.java`**

~~~java
package com.example.restauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(RestAuthApplication.class, args);
    }
}
~~~

### 7.2. Shared Error JSON Types

**`src/main/java/com/example/restauth/ApiError.java`**

~~~java
package com.example.restauth;

// Java record enabling Jackson to serialize JSON {"code": "...", "message": "..."}.
public record ApiError(String code, String message) {
}
~~~

**`src/main/java/com/example/restauth/ApiErrors.java`**

~~~java
package com.example.restauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;

public final class ApiErrors {

    private ApiErrors() {
    }

    public static void write(ObjectMapper mapper, HttpServletResponse response,
                             int status, String code, String message)
            throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        if (status == HttpServletResponse.SC_UNAUTHORIZED) {
            response.setHeader("WWW-Authenticate", "Bearer");
        }

        mapper.writeValue(response.getWriter(), new ApiError(code, message));
    }
}
~~~

This helper writes only error JSON **safely chosen** by server-side code. It never takes or prints `AuthenticationException#getMessage`. `WWW-Authenticate: Bearer` is added for 401 responses on Bearer-protected endpoints. If the system uses HTTP Basic or sessions, the challenge header must change accordingly.

### 7.3. TokenService: Issuing and Looking Up Demo Tokens

**`src/main/java/com/example/restauth/TokenService.java`**

~~~java
package com.example.restauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Service;

@Service
public class TokenService {

    public static final long TOKEN_SECONDS = 900;

    private final SecureRandom random = new SecureRandom();
    private final ConcurrentMap<String, TokenRecord> tokens =
        new ConcurrentHashMap<>();

    private record TokenRecord(
        String username,
        Set<String> authorityNames,
        Instant expiresAt
    ) {
    }

    public String issue(Authentication authenticated) {
        byte[] secret = new byte[32];
        random.nextBytes(secret);

        String rawToken = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(secret);

        Arrays.fill(secret, (byte) 0);

        Set<String> authorityNames = authenticated.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toUnmodifiableSet());

        TokenRecord record = new TokenRecord(
            authenticated.getName(),
            authorityNames,
            Instant.now().plus(Duration.ofSeconds(TOKEN_SECONDS))
        );

        // Store SHA-256 fingerprint instead of plaintext token in the map.
        tokens.put(fingerprint(rawToken), record);
        return rawToken;
    }

    public Optional<Authentication> authenticate(String token) {
        // Token in this example: Base64URL of 32 bytes -> 43 chars.
        if (token == null || !token.matches("[A-Za-z0-9_-]{43}")) {
            return Optional.empty();
        }

        String key = fingerprint(token);
        TokenRecord record = tokens.get(key);

        if (record == null) {
            return Optional.empty();
        }

        if (!Instant.now().isBefore(record.expiresAt())) {
            tokens.remove(key, record);
            return Optional.empty();
        }

        var granted = record.authorityNames().stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

        Authentication result = UsernamePasswordAuthenticationToken.authenticated(
            record.username(), null, granted
        );
        return Optional.of(result);
    }

    private static String fingerprint(String token) {
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            byte[] digest = sha256.digest(
                token.getBytes(StandardCharsets.US_ASCII)
            );
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

**Explanation:**

- Tokens generated from **32 random bytes** have very high entropy; the bytes are URL-safe Base64 encoded into 43 characters, not a username/password.
- The map stores only the **SHA-256 fingerprint of the token**, never retaining the plaintext token as a key; this reduces data exposure in RAM, though it is not a replacement for a vault/KMS or memory controls.
- TTL is checked on token use. If expired, it returns empty and removes the entry. Tokens never accessed after expiry can remain in the map, so production stores need **real TTL eviction**.
- Authorities are snapshotted at issuance time. If an admin revokes permissions or locks an account, an existing demo token **can still work until its TTL expires**, because the database is not re-queried per request. Production needs revocation/revalidation/risk-appropriate lifetimes.
- `UsernamePasswordAuthenticationToken.authenticated(...)` is created here **only after** locating a valid, unexpired server-issued random token in the server-controlled token store. Never do the equivalent from client-supplied roles.
- `ConcurrentHashMap` is safe only within a **single JVM**, not a distributed session store, and provides no auditing, concurrency policy, or cluster synchronization for real systems.

### 7.4. BearerTokenFilter: Verifying Every Request

**`src/main/java/com/example/restauth/BearerTokenFilter.java`**

~~~java
package com.example.restauth;

import java.io.IOException;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class BearerTokenFilter extends OncePerRequestFilter {

    private final TokenService tokens;
    private final ObjectMapper mapper;

    public BearerTokenFilter(TokenService tokens, ObjectMapper mapper) {
        this.tokens = tokens;
        this.mapper = mapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();

        // Login checks username/password; do not use old Bearer token.
        return !path.startsWith("/api/")
            || path.equals("/api/auth/login");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String authorization = request.getHeader("Authorization");

        if (authorization == null) {
            // Public or anonymous URLs will be evaluated by authorizeHttpRequests.
            chain.doFilter(request, response);
            return;
        }

        if (!authorization.startsWith("Bearer ")) {
            reject(response);
            return;
        }

        String rawToken = authorization.substring("Bearer ".length());
        Optional<Authentication> authenticated = tokens.authenticate(rawToken);

        if (authenticated.isEmpty()) {
            reject(response);
            return;
        }

        // Create a NEW context for the current request; do not mutate existing instance.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated.get());
        SecurityContextHolder.setContext(context);

        // Spring Security's SecurityContextHolderFilter handles clearing the holder.
        chain.doFilter(request, response);
    }

    private void reject(HttpServletResponse response) throws IOException {
        ApiErrors.write(mapper, response,
            HttpServletResponse.SC_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Valid authentication is required.");
    }
}
~~~

**Pitfall to avoid:** this filter class is **not annotated with `@Component` and not declared as a Servlet `Filter` bean**. It is instantiated inside `SecurityConfig` and added **only once** via `http.addFilterBefore(...)`. If a `Filter` is both a Spring bean auto-registered by Boot in the servlet container and added to the security filter chain, it can run twice or in the wrong order.

This is a **minimal demo** parser/token filter accepting only `Bearer <43 Base64URL chars>`. Under HTTP standards, authentication schemes have specific parsing/case rules; production should use **Spring Security OAuth2 Resource Server** or a vetted Bearer parser implementation rather than copying this parser as-is.

### 7.5. SecurityConfig: AuthenticationManager and JSON 401/403

**`src/main/java/com/example/restauth/SecurityConfig.java`**

~~~java
package com.example.restauth;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),

            User.withUsername("admin")
                .password(hash)
                .roles("ADMIN")
                .build(),

            User.withUsername("locked")
                .password(hash)
                .roles("USER")
                .accountLocked(true)
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            TokenService tokens,
            ObjectMapper mapper) throws Exception {

        // Instantiate filter directly; do not let Boot auto-register
        // it as a Servlet Filter outside Spring Security.
        BearerTokenFilter bearerFilter = new BearerTokenFilter(tokens, mapper);

        return http
            // ONLY appropriate for stateless Bearer header, not using session cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)

            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    ApiErrors.write(mapper, response, 401,
                        "UNAUTHORIZED",
                        "Valid authentication is required."))
                .accessDeniedHandler((request, response, exception) ->
                    ApiErrors.write(mapper, response, 403,
                        "FORBIDDEN",
                        "You do not have permission to access this resource."))
            )

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )

            .addFilterBefore(
                bearerFilter,
                UsernamePasswordAuthenticationFilter.class
            )
            .build();
    }
}
~~~

In this example, `httpBasic` and `formLogin` are disabled so the API **never redirects 302** or renders HTML login pages. The controller accepts JSON username/password directly. `csrf` is disabled **because the stateless demo does not use cookies as credentials**; never copy this setting into cookie/session web apps. `ExceptionTranslationFilter` and the custom handlers return JSON responses for 401/403 resource failures.

### 7.6. ApiController: 200, 400, 401, and Protected APIs

**`src/main/java/com/example/restauth/ApiController.java`**

~~~java
package com.example.restauth;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    private final AuthenticationManager authenticationManager;
    private final TokenService tokens;

    public ApiController(
            AuthenticationManager authenticationManager,
            TokenService tokens) {
        this.authenticationManager = authenticationManager;
        this.tokens = tokens;
    }

    public record LoginRequest(String username, String password) {
    }

    public record LoginSuccess(
        String tokenType,
        String accessToken,
        long expiresIn
    ) {
    }

    public record Profile(String username) {
    }

    @PostMapping(
        path = "/auth/login",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> login(@RequestBody LoginRequest request) {
        if (request == null ||
            request.username() == null || request.username().isBlank() ||
            request.password() == null || request.password().isBlank()) {

            return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                    "INVALID_REQUEST", "Invalid request."));
        }

        try {
            Authentication authenticated = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    request.username(), request.password()
                )
            );

            String token = tokens.issue(authenticated);
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginSuccess(
                    "Bearer", token, TokenService.TOKEN_SECONDS));

        } catch (AuthenticationException ex) {
            // All credential/account-state errors share the same public response.
            // Never return ex.getMessage() or the exception class.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                    "AUTHENTICATION_FAILED",
                    "Invalid login credentials."));
        }
    }

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/me")
    public Profile me(Authentication authentication) {
        return new Profile(authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }
}
~~~

This is the **custom login in a REST controller model**: `AuthenticationManager` decides authentication; the controller decides the HTTP response; `formLogin().successHandler(...)` or `failureHandler(...)` is not needed for this route. A token issued after successful authentication **does not automatically update a session**, and the client must resend the token on every request.

If authentication succeeds yet token issuance encounters a system error, never return a fake 200 "login succeeded" when the client has no usable credential. Return a safe 5xx via error handling and raise operational alerts. Never catch every `RuntimeException` and convert it to 401; that hides infrastructure failures.

### 7.7. ApiExceptionAdvice: Malformed JSON Errors Are Also JSON

**`src/main/java/com/example/restauth/ApiExceptionAdvice.java`**

~~~java
package com.example.restauth;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableJson(
            HttpMessageNotReadableException exception) {

        // Never return exception.getMessage(): may leak parser details.
        return ResponseEntity.badRequest()
            .cacheControl(CacheControl.noStore())
            .body(new ApiError(
                "INVALID_REQUEST", "Invalid request."));
    }
}
~~~

This advice handles unreadable JSON. Other errors such as 415 unsupported media type, 405 method not allowed, custom validation, 404, and 5xx may need their own error contract if the project requires **all** error responses to share the same JSON schema. Never expose stack traces publicly; in production implement comprehensive error handling and observability.

### 7.8. Testing with Spring Security MockMvc

**`src/test/java/com/example/restauth/AuthApiTests.java`**

~~~java
package com.example.restauth;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthApiTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    private MvcResult login(String username, String password)
            throws Exception {

        return mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of(
                    "username", username,
                    "password", password
                ))))
            .andReturn();
    }

    private String successfulToken(String username) throws Exception {
        MvcResult login = mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of(
                    "username", username,
                    "password", "demo-pass"
                ))))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.accessToken").isNotEmpty())
            .andExpect(jsonPath("$.expiresIn").value(900))
            .andReturn();

        return mapper.readTree(
            login.getResponse().getContentAsString()
        ).get("accessToken").asText();
    }

    @Test
    void loginAndReadResource() throws Exception {
        String token = successfulToken("alice");

        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void allCredentialFailuresAreGeneric() throws Exception {
        for (Map<String, String> credentials : new Map[] {
                Map.of("username", "alice", "password", "wrong"),
                Map.of("username", "does-not-exist", "password", "demo-pass"),
                Map.of("username", "locked", "password", "demo-pass")
        }) {
            mvc.perform(post("/api/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(mapper.writeValueAsString(credentials)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_FAILED"))
                .andExpect(jsonPath("$.message").value(
                    "Invalid login credentials."));
        }
    }

    @Test
    void invalidJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not valid json"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void missingAndFakeBearerAreUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
            .andExpect(header().string("WWW-Authenticate", "Bearer"));

        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer not-a-real-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void validUserWithoutRoleGetsForbidden() throws Exception {
        String token = successfulToken("alice");

        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void adminTokenCanAccessAdmin() throws Exception {
        String token = successfulToken("admin");

        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }
}
~~~

**Technical note on the test:** In `allCredentialFailuresAreGeneric`, the Java code uses a generic `Map[]` array to group cases; some compilers may emit an `unchecked` warning on the foreach loop. The warning does not affect results, though in production code you should switch to `List.of(Map.of(...), ...)` for type safety. The same principle applies when expanding tests for disabled/expired accounts.

This test group does not use `@WithMockUser` to simulate login success because it needs to test **the real path of JSON credentials and tokens**. `@WithMockUser` is useful for isolated authorization tests, but it does not prove the login endpoint or token service works.

### 7.9. Running the Project and Observing

Requires JDK 17+, Maven, and dependency downloads on first build:

~~~bash
mvn test
mvn spring-boot:run
~~~

The **expected** result after `mvn test` is a passing build/test run if the environment has the required dependencies. These tests and commands **have not been executed in this document**, so do not treat the results as directly observed output.

In another terminal, using curl (PowerShell may require `curl.exe`):

~~~bash
curl -i http://localhost:8080/api/public
# Expected 200; body {"status":"public-ok"}

curl -i http://localhost:8080/api/me
# Expected 401; JSON code UNAUTHORIZED

curl -i -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"wrong"}'
# Expected 401; JSON code AUTHENTICATION_FAILED

curl -i -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"demo-pass"}'
# Expected 200; JSON tokenType, accessToken, expiresIn
~~~

**Never copy real tokens into docs/logs/chat.** In a learning environment, take the `accessToken` value from the response on your local machine and call:

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'Authorization: Bearer REPLACE_WITH_TEST_TOKEN'
# Expected 200; {"username":"alice"}

curl -i http://localhost:8080/api/admin \
  -H 'Authorization: Bearer REPLACE_WITH_TEST_TOKEN'
# Expected 403; {"code":"FORBIDDEN",...}
~~~

The two lines using `REPLACE_WITH_TEST_TOKEN` are just placeholders in illustrative commands, **not valid tokens**. With an admin token obtained by logging in with username `admin` and password `demo-pass`, `GET /api/admin` will receive JSON `{"status":"admin-ok"}`.

**Sample results are not proof the code ran.** Actual building and testing require Maven/JDK, runtime logs, and matching HTTP observation; any change to the API contract must update tests.

## 8. Why Do 401, 403, and 302 Differ in Spring Security?

### 8.1. Unauthenticated Request

When `GET /api/me` lacks a Bearer token, `BearerTokenFilter` lets the request proceed with no user in the security context. The `anyRequest().authenticated()` rule requires a user, so `ExceptionTranslationFilter` uses `AuthenticationEntryPoint` to return **401 JSON**. Because form login is disabled, there is no `302 /login` redirect.

### 8.2. Token Present but Invalid

If the client sends `Authorization: Bearer xyz`, the filter validates format and the token store, then proactively returns a uniform **401 JSON**. Never include details like "token exists but just expired" in the response. The client only needs to know it must obtain a valid credential again.

### 8.3. Valid Token but Lacking Role

When the client has a valid token for alice with authority `ROLE_USER`, the filter creates `Authentication` and sets it in the context; requesting `/api/admin` requires `ROLE_ADMIN`, so `AccessDeniedHandler` returns **403 JSON**. This is not a username/password error from the earlier login.

### 8.4. Failed JSON Login

When a client sends the wrong password, `DaoAuthenticationProvider` throws `AuthenticationException` and the controller catches **that exact exception type** to return 401. Never catch `Exception` and treat every database, serialization, or token-store outage as "bad credentials".

### 8.5. Invalid JSON

Spring MVC's parser throws `HttpMessageNotReadableException`; `@RestControllerAdvice` returns **400 JSON**. Parser errors occur outside `AuthenticationManager`, so they do not pass through `AuthenticationFailureHandler`. This is an important distinction when writing custom REST logins.

## 9. Risks When Writing Custom REST Authentication

### 9.1. Do Not Rely on Status Alone to Identify Errors

Clients should inspect both the HTTP status and the stable `code`. For example, 401 from login and 401 from a protected resource both signify unauthenticated state, yet recovery differs: login 401 calls for checking credentials; resource 401 may call for a fresh token. Still, never let differences become a channel leaking account state.

### 9.2. Do Not Leak Internal Authentication Reasons

Returning the same public 401 for wrong password, non-existent username, and locked/disabled accounts is practical advice to curb user enumeration. However, **identical response bodies are not enough** if timing, response size, headers, rate-limit policies, or other recovery endpoints reveal account status.

Implement signal-based rate limiting, detection, auditing, MFA, and identity-verified recovery flows. Never echo exception messages/classes or raw usernames/passwords into URLs and logs.

### 9.3. Avoid Rolling Your Own Token Infrastructure When Standard Infrastructure Exists

The demo uses a hand-rolled opaque token to show 200/401/403. In production:

- Prefer **Spring Security OAuth2 Resource Server** with JWT/opaque token introspection, or a properly operated authorization server/IdP.
- Configure expiry, refresh, revocation/blacklisting, rotation, issuer/audience/scope, HTTPS transport, and protection against XSS/token theft.
- Use a distributed store with TTL eviction, access control, auditing, scalability, and resilience across backend restarts.
- Never put tokens in query strings or HTML, never log Authorization headers, and never return tokens in exceptions.
- For JWTs, never merely decode payloads; verify signatures/algorithms/keys/claims against trusted configurations.

### 9.4. Authorization Must Still Enforce Business Rules

A valid token does not mean a user can view all data. When accessing orders, invoices, or multi-tenant data, services must check **ownership, tenant scope, and per-object permissions**, not just `authenticated()`. Returning 403 or 404 per resource-hiding policy may be appropriate; never reveal the existence of sensitive objects to unauthorized callers.

### 9.5. CSRF and CORS Are Not the Same Problem

In the demo, clients attach Bearer tokens via headers and the server does not use session cookies as auth credentials, so disabling CSRF in security config has a sound basis for that model. If browsers use cookies or HTTP Basic sent automatically, CSRF risk must be assessed separately. **CORS does not replace CSRF** and is not authentication; it restricts cross-origin browser reads/sends by policy without stopping non-browser clients from calling the API.

### 9.6. Logging and Observability

Logs should include request IDs, endpoints, timestamps, normalized internal failure categories, and minimal operational context with proper access controls. Never log plaintext passwords, tokens, cookies, full Authorization headers, or stack traces into responses. While public error outputs stay uniform, internal observability must remain detailed enough to diagnose infrastructure outages instead of turning everything into 401.

### 9.7. Caching and Personal Data

Access-token responses must include `Cache-Control: no-store`, use HTTPS, and minimize user data. Resources with sensitive data also need appropriate cache policies. Never extrapolate from the demo's JSON response containing only a username that personal profiles may be cached publicly.

## 10. Pre-Production Testing Checklist for REST Login

**Input and authentication**

1. Schema-valid JSON + valid credentials → 200 with contract-compliant token.
2. Non-existent username, wrong password, locked/disabled/expired account → 401 with generic message, without leaking user state.
3. Malformed JSON or missing field → 400 JSON, without leaking parser stack traces.
4. Wrong `Content-Type`/method → consistent 415/405 policy or error mapping.
5. High login attempt rates → throttling/rate limiting/auditing policies; do not rely solely on BCrypt cost.

**Tokens and authorization**

6. Missing Bearer → 401 + appropriate challenge.
7. Tampered, malformed, expired, or revoked token → 401.
8. Valid token lacking permission → 403.
9. Valid token with sufficient permission → endpoint returns expected data.
10. User A's token cannot read/modify data belonging solely to user B; tenant isolation tested.
11. Restarts/redeploys/multi-instance/secret rotation work per production design, without relying on the demo in-memory store.

**Responses and lifecycle**

12. 401/403 errors have appropriate `Content-Type`, stable JSON schema, and no unexpected 302/HTML redirects.
13. Login success never returns passwords/secrets; token sits in the specified field with `Cache-Control: no-store`.
14. Logging systems contain no tokens/passwords/Authorization headers.
15. Clients handle expiration, refresh/logout, retries, and 429 per contract; no infinite retry loops on 401.
16. CORS/CSRF, HTTPS, security headers, and session policies match actual credential types.
17. Test 5xx failures, DB outages, and token store outages; never disguise operational errors as "bad credentials".

## 11. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Failed login returns 403 because they don't have permission." | Invalid credentials are usually **401**; authenticated yet missing roles is usually **403** |
| "REST login can use `failureUrl` to navigate to HTML." | API clients usually need **consistent JSON/status**, not form redirects |
| "Using `AuthenticationSuccessHandler` creates a session/token automatically in any custom filter." | A success handler only responds per your code; persistence/issuance must be configured properly |
| "Returning 200 with body success=false for all errors is enough." | HTTP status still needs to be accurate for clients and infrastructure |
| "`AuthenticationFailureHandler` handles all 403s and JSON parse failures." | It handles filter-level authentication failures, not MVC validation/authorization/CSRF |
| "User does not exist, so return USER_NOT_FOUND to ease debugging." | Enables user enumeration; public endpoints should usually return generic credential errors |
| "Having a Bearer token guarantees the token is still valid." | Must verify issuer/store, expiry, scope, and revocation policy |
| "Once a 200 token is issued, the account is allowed to call every endpoint." | Authorization must still enforce roles/permissions/ownership |
| "Putting tokens in URLs is more convenient for clients." | URLs leak easily in logs/history/referrers; use the Authorization header |
| "Just disable CSRF for all REST APIs." | Depends on credentials; **cookie-based auth still requires CSRF evaluation** |
| "Register a filter as @Component and also call addFilterBefore." | Boot can auto-register it outside the Security chain and run it twice |
| "Tokens stored in ConcurrentHashMap make a production token service." | Lacks distribution, TTL eviction, revocation, auditing, and durability |
| "Same 401 JSON prevents all enumeration." | Timing, headers, response sizes, recovery endpoints, and rate-limit behavior still matter |
| "Catch(Exception) and return 401 keeps the API simple." | Masks infrastructure failures and creates a broken contract that hides incidents |

## 12. Self-Check

**1.** Login API receives valid JSON but wrong password. What should it return?

**Answer:** Typically **401** and a generic public error code such as `AUTHENTICATION_FAILED`; never confirm whether the username exists or is locked.

**2.** User is logged in and sends a valid Bearer token, yet lacks `ROLE_ADMIN` for `/api/admin`?

**Answer:** Typically **403** from authorization/`AccessDeniedHandler`; not a login error to route to `AuthenticationFailureHandler`.

**3.** `POST /api/auth/login` body contains syntactically invalid JSON?

**Answer:** **400** from MVC exception handling; not yet a wrong-password case.

**4.** Does `AuthenticationSuccessHandler` automatically issue a JWT or save a session?

**Answer:** No. The handler must explicitly invoke an appropriate token-issuance or security-context persistence mechanism. Returning 200 does not grant access to subsequent requests.

**5.** Why shouldn't a resource API redirect `302 /login` when a token is missing?

**Answer:** API clients need HTTP 401 JSON/an appropriate challenge to know credentials are needed; HTML redirects break API contracts and retry logic.

**6.** Why not send `LockedException` and account-disabled messages in the response?

**Answer:** Those states let unauthenticated callers enumerate users and infer internal status. Keep public responses generic, audit securely internally, and handle recovery only after verifying identity.

**7.** Why does the example use `SecurityContextHolder.createEmptyContext()` in the bearer filter?

**Answer:** To attach the verified `Authentication` to a fresh `SecurityContext` for the current request without mutating a context that might be shared from elsewhere.

**8.** If a real app uses cookies/sessions instead of Bearer headers, can you copy `csrf.disable()` verbatim?

**Answer:** No. Browser-attached credentials carry CSRF risk; you must design appropriate CSRF/cookie/session policies.

**9.** Why can't the example's in-memory token store be used directly across multiple production servers?

**Answer:** Each JVM has its own map, restarts wipe tokens, and it lacks distributed storage, revocation, or complete TTL eviction. Reliable token infrastructure is required.

**10.** When authentication fails due to a database outage, is catching all `Exception`s and returning 401 right?

**Answer:** No. System outages must be handled and monitored as operational errors with appropriate 5xx codes and safe messages, never disguised as wrong passwords.

**Remember:** **REST authentication responses must accurately reflect state: 200 on login success, 400 on bad request, 401 when not validly authenticated, 403 when authenticated yet lacking permission.** Use a stable JSON contract without leaking account state, separate controller/filter success-failure handling from entry points/access-denied handlers, and manage tokens/sessions consistently with your chosen mechanism.