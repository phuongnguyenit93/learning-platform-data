# Session-Based JSON Login, Custom Principal, and Safe Logout

## 1. The Problem: A JSON API That Still Uses Login Sessions

A **Spring Boot + Spring Security Servlet** application may serve a JavaScript frontend or HTML pages that submit login credentials via JSON, use a session cookie to maintain authentication state, and call subsequent APIs under that same session. The goal differs from a pure bearer-token API:

- The client calls `GET /api/auth/csrf` to obtain a CSRF token along with an anonymous session.
- The client sends `POST /api/auth/login` with a JSON body `{"username":"alice","password":"..."}` and a valid CSRF header.
- The backend uses `AuthenticationManager` to verify the credentials, builds a **custom principal** containing an immutable ID/tenant, prevents **session fixation**, writes `Authentication` into `SecurityContext`, and **saves the context into the HTTP session**.
- The browser retains the `JSESSIONID` cookie so subsequent requests are authenticated by the session.
- `GET /api/me` allows only logged-in users and returns a safe DTO (never returning password hashes or `SecurityContext`).
- `POST /api/auth/logout` requires a CSRF token and terminates the session, clearing authentication. After logout, the old session must no longer grant access.

**Key takeaway:** returning `200 OK` after `AuthenticationManager.authenticate(...)` **does not automatically mean** subsequent requests are logged in. In Spring Security 6, when writing a custom login controller, you must explicitly manage the lifecycle of `SecurityContextRepository` and `SessionAuthenticationStrategy`, instead of expecting the default login filter to do it for you.

This practice uses Spring Boot **3.3.5**, Spring MVC/Servlet, Java **17+**, Java records for DTOs, `DaoAuthenticationProvider`, BCrypt, session cookies, `HttpSessionCsrfTokenRepository`, `HttpSessionSecurityContextRepository`, and MockMvc. Do not use `csrf().disable()` just for login convenience; JSON login with session cookies still carries CSRF risk.

## 2. Overview Diagram of the Request Flow

```text
SAME-ORIGIN BROWSER                SPRING BOOT SERVLET
        |                                   |
        | GET /api/auth/csrf                |
        |---------------------------------->|
        |  CsrfFilter -> HttpSessionCsrfTokenRepository
        |<----------------------------------|
        | JSESSIONID cookie + CSRF token    |
        |                                   |
        | POST /api/auth/login              |
        | Cookie: JSESSIONID                |
        | X-CSRF-TOKEN: <token>             |
        | JSON {username,password}          |
        |---------------------------------->|
        | CsrfFilter validates token        |
        | AuthController                    |
        | AuthenticationManager             |
        |  -> DaoAuthenticationProvider     |
        |  -> PasswordEncoder.matches(...)  |
        |  -> UserDetailsService            |
        | SessionAuthenticationStrategy     |
        |  -> changeSessionId()             |
        |  -> clear old login CSRF token    |
        | SecurityContextRepository         |
        |  -> saveContext into HTTP session |
        |<----------------------------------|
        | 200 JSON user-safe DTO            |
        |                                   |
        | GET /api/me + session cookie      |
        |---------------------------------->|
        | SecurityContextHolderFilter       |
        |  -> load Authentication from sess.|
        | AuthorizationFilter -> authenticated()
        |<----------------------------------|
        | 200 JSON user metadata            |
        |                                   |
        | GET /api/auth/csrf (fresh token)  |
        |---------------------------------->|
        |<----------------------------------|
        | POST /api/auth/logout + CSRF      |
        |---------------------------------->|
        | CsrfFilter -> LogoutFilter        |
        | -> SecurityContextLogoutHandler   |
        | -> session.invalidate()           |
        | -> CsrfLogoutHandler              |
        |<----------------------------------|
        | 204 No Content; cookie expired    |
```

Some common misconceptions:

1. **A CSRF token is not a session ID.** The CSRF token proves a state-changing request came from a client authorized to use a valid session under the anti-CSRF contract; it is not used to verify passwords.
2. **Session fixation protection** rotates the session ID upon successful login; never keep the pre-login anonymous session ID as the ID of the authenticated session.
3. **The custom principal** must come from trusted backend data **after authentication**. The client must never send `role=ADMIN`, `userId`, or `tenantId` to dictate permissions.
4. **Logout** terminates authentication state on the server; deleting the cookie on the frontend alone is insufficient if the server session remains active.
5. When session cookies are sent automatically by the browser, CSRF protection is separate from authentication/authorization and **cannot be replaced by CORS**.

## 3. Why Use HTTP Sessions Instead of JWT?

Session cookies fit well when the browser and backend share the same origin or have a controlled cookie relationship:

| Aspect | Session cookie | Bearer JWT |
| --- | --- | --- |
| Login state | Server stores `SecurityContext` in session | Caller sends bearer token and Resource Server verifies it |
| Session revocation | Server can `invalidate()` session, delete from store | Requires appropriate expiry/revocation/token lifecycle |
| Browser requests | Browser auto-sends cookie per domain/path/SameSite | Frontend or client must manage the token |
| CSRF | Critical whenever cookies are auto-sent | Does not disappear if JWT is also stored in a cookie |
| Multi-instance scaling | Needs sticky sessions or shared store like Spring Session | Token validation can be stateless depending on design |
| Permission changes | Must update/invalidate context in session | Needs a strategy to refresh/revoke tokens/claims |

**Neither choice is automatically safer in all cases.** If the UI is a browser app needing instant logout and a backend session, session cookies can be simpler. If the API serves mobile/server-to-server clients or needs a decoupled identity provider, a Resource Server fits better.

In this practice, we choose sessions to thoroughly learn **storing and clearing authentication across the Servlet lifecycle**.

## 4. Key Spring Security Components to Know

| Component | Responsibility | Notes |
| --- | --- | --- |
| `SecurityFilterChain` | Protects URLs, configures CSRF/logout/security context | Must cover login, CSRF, API, and logout routes |
| `AuthenticationManager` | Processes an authentication request | Calling `authenticate()` alone does not create a session cookie |
| `DaoAuthenticationProvider` | Queries `UserDetailsService`, checks password via `PasswordEncoder` | Demo uses BCrypt; never use `{noop}` in production |
| `UserDetailsService` | Loads username/password hash/authorities from backend | Never accept `roles` from client JSON |
| `SecurityContext` | Holds the request's verified `Authentication` | Created fresh after successful login |
| `SecurityContextHolder` | Holds context for the request thread | Typically ThreadLocal; not session storage |
| `SecurityContextRepository` | Loads/saves context across requests | Example uses `HttpSessionSecurityContextRepository` |
| `SessionAuthenticationStrategy` | Enforces policy on login success | Demo rotates session ID and refreshes CSRF |
| `CsrfFilter`/`CsrfTokenRepository` | Checks side-effecting requests originate from allowed client | Login/logout use POST with CSRF token |
| `LogoutFilter` | Intercepts logout requests and invokes `LogoutHandler`s | Never expose a public GET logout endpoint |

A custom controller that only calls:

```java
Authentication result = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
```

has only completed **credential verification**. Session handling, context persistence, and logout do not happen automatically if you bypass Spring Security's default login filter.

## 5. Security Principles Before Writing Code

This demo follows these decisions:

1. **Login via POST JSON**, never putting passwords in URLs, query strings, or `GET`.
2. **Keep CSRF enabled** for state-changing requests relying on session cookies; both login and logout require a valid token.
3. **BCryptPasswordEncoder** for password hashing; the demo uses one fixed account on `127.0.0.1` only, storing no plaintext passwords in the user store.
4. **Never return passwords/hashes** in JSON responses or the principal's `toString()`.
5. **Custom principal** holds only `userId`, `username`, and `tenantId`; authorities come from a trusted backend user source.
6. **Rotate session ID after authentication** to prevent session fixation; if the app needs concurrent session control, add the corresponding session strategies.
7. **Save context explicitly** with `SecurityContextRepository.saveContext(...)` so the next request sees the user; do not treat `SecurityContextHolder.setContext(...)` as persistence.
8. **Logout via POST** handled by `LogoutFilter`, invalidating the session and requesting cookie deletion; the CSRF token is also cleared from the session.
9. **Auth responses are non-cacheable**, using only a same-origin client in the demo, never opening CORS `*` with credentials.
10. **Enforce session/tenant/authorization binding** on the backend; never trust a browser-supplied `tenantId` as proof of data access.

## 6. Runnable Java 17+ Project Structure

```text
json-session-login/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/jsonsession/
    │   │   ├── JsonSessionApplication.java
    │   │   ├── AppPrincipal.java
    │   │   ├── SecurityConfig.java
    │   │   └── AuthController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/java/demo/jsonsession/
        └── JsonSessionIntegrationTest.java
```

The demo uses Java 17 records and Jakarta Validation. Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Requires a Java 17-compatible Gradle wrapper; if the folder has `gradlew`/`gradlew.bat`, use the wrapper; otherwise install a compatible Gradle version and generate the wrapper per your project build process. The files below belong to the Java project, not standalone snippets to paste into a class without imports.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

Local development uses HTTP **on loopback only**, so `Secure` is omitted in the dev config so cookies work on `http://127.0.0.1`. Production must use HTTPS and `Secure=true` as shown in the deployment section at the end; never transmit real credentials over plain HTTP.

Create `src/main/java/demo/jsonsession/JsonSessionApplication.java`:

```java
package demo.jsonsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonSessionApplication.class, args);
    }
}
```

## 7. Custom Principal: Holding Only Backend-Verified Identity

Create `src/main/java/demo/jsonsession/AppPrincipal.java`:

```java
package demo.jsonsession;

import java.io.Serial;
import java.io.Serializable;
import java.security.Principal;

public record AppPrincipal(
        String userId,
        String username,
        String tenantId) implements Principal, Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    @Override
    public String getName() {
        return username;
    }
}
```

This is an **application principal** containing no password, hash, raw HTTP cookie, token, or client-claimed permissions.

Why does the record implement `Principal`?

- `Authentication#getPrincipal()` can hold `AppPrincipal` so services/controllers access the authoritative ID and tenant.
- `Principal#getName()` allows Spring Security and Spring MVC to read `Authentication#getName()` cleanly.
- `Serializable` makes the principal compatible with HTTP session storage that serializes attributes. In clusters, session serialization and schema migration must still be tested explicitly.
- An immutable record prevents mutating a principal's `tenantId` from a worker thread while the session is used concurrently.

In production, `userId` and `tenantId` must be looked up from a **trusted account directory / server-side database** after `AuthenticationManager` succeeds. The demo maps a single known `alice` account statically; never do this:

```java
// Unsafe: the client has no authority to supply its own principal/tenant.
new AppPrincipal(json.userId(), json.username(), json.tenantId());
```

Multi-tenant systems must verify at the service layer that the user is authorized to access **each tenant-owned resource**, rather than relying solely on the presence of a tenant ID on the principal. A session can become stale when a user is locked or moved between tenants; proper revocation or revalidation is required.

## 8. Security Configuration: Provider, Session, CSRF, and Logout

Create `src/main/java/demo/jsonsession/SecurityConfig.java`:

```java
package demo.jsonsession;

import java.util.List;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Fixed password for local learning on 127.0.0.1 only.
        // Store keeps only the BCrypt hash, never the plain password.
        String hash = encoder.encode("demo-only");

        return username -> {
            if (!"alice".equals(username)) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername("alice")
                    .password(hash)
                    .roles("USER")
                    .build();
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfRepository)
            throws Exception {

        return http
                .securityContext(context -> context
                        .securityContextRepository(contextRepository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .csrf(csrf -> csrf
                        .csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/auth/csrf").permitAll()
                        .requestMatchers(HttpMethod.POST,
                                "/api/auth/login").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyRequest().denyAll())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((request, response, error) -> {
                            response.setStatus(
                                    HttpServletResponse.SC_UNAUTHORIZED);
                            response.setContentType(
                                    MediaType.APPLICATION_JSON_VALUE);
                            response.getWriter()
                                    .write("{\"error\":\"unauthorized\"}");
                        }))
                .logout(logout -> logout
                        .logoutUrl("/api/auth/logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .logoutSuccessHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT)))
                .build();
    }
}
```

### 8.1. Why Are These Beans Declared Explicitly?

**`AuthenticationManager`:** the demo wires `DaoAuthenticationProvider` with `UserDetailsService` and `PasswordEncoder` under a single contract. Do not confuse `ProviderNotFoundException` with a wrong password: the provider is registered specifically for `UsernamePasswordAuthenticationToken`.

**`HttpSessionSecurityContextRepository`:** Spring Security 6 typically requires an **explicit save** when you build `Authentication` yourself. The exact same repository instance is shared between the filter chain and the controller, so the next request loads the saved context from the session. Calling `SecurityContextHolder.setContext(context)` alone is not enough.

**`SessionAuthenticationStrategy`:** because the controller performs login itself, it must invoke the session strategy after authentication succeeds. The demo rotates the session ID via `ChangeSessionIdAuthenticationStrategy` and refreshes CSRF state via `CsrfAuthenticationStrategy`. With the default form login filter, the framework runs these automatically; with a custom MVC controller, you must not skip them.

**`HttpSessionCsrfTokenRepository`:** the CSRF token is stored in the session. `/api/auth/csrf` exposes the token to the same-origin browser using that session. This GET may create an anonymous session to hold the token; that is not a vulnerability by itself, though resource usage and cookie policies must be controlled.

**`SessionCreationPolicy.IF_REQUIRED`:** allows creating a session when needed for login/CSRF. Do not use `STATELESS` if you expect `JSESSIONID` and `SecurityContext` to persist across requests.

**Logout:** `.logoutUrl("/api/auth/logout")` is handled by `LogoutFilter` (before any controller), using POST with CSRF enabled; default handlers clear authentication, invalidate the session, and remove the CSRF token per the logout lifecycle. `deleteCookies("JSESSIONID")` is only a hint to clear the browser cookie: actual effectiveness depends on path/domain/flags; **invalidating the server-side session** is the decisive revocation step.

### 8.2. Why Is There No `formLogin` or `httpBasic`?

Because this endpoint is designed to **accept JSON**, not form parameters or an Authorization Basic header. `AuthenticationManager` is invoked inside the controller to authenticate. There is no need to enable `formLogin()` for a JSON API if you do not want its default endpoints or redirects. However, writing custom login precisely requires handling session fixation, security context saving, CSRF, and the HTTP error contract explicitly.

**Version note:** the `DaoAuthenticationProvider` setters shown follow Spring Security 6.x paired with Boot 3.3.5; newer framework lines may require different constructors or configuration. When upgrading, adopt the matching API and re-run tests instead of assuming this code stays unchanged forever.

## 9. JSON Login Controller, CSRF Bootstrap, and `/api/me`

Create `src/main/java/demo/jsonsession/AuthController.java`:

```java
package demo.jsonsession;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final AuthenticationManager authManager;
    private final SessionAuthenticationStrategy sessionStrategy;
    private final SecurityContextRepository contextRepository;

    public AuthController(
            AuthenticationManager authManager,
            SessionAuthenticationStrategy sessionStrategy,
            SecurityContextRepository contextRepository) {
        this.authManager = authManager;
        this.sessionStrategy = sessionStrategy;
        this.contextRepository = contextRepository;
    }

    public record LoginRequest(
            @NotBlank @Size(max = 100) String username,
            @NotBlank String password) {

        // Prevent accidentally printing the password via record.toString().
        @Override
        public String toString() {
            return "LoginRequest[REDACTED]";
        }
    }

    public record UserView(
            String userId, String username, String tenantId) {}

    @GetMapping("/auth/csrf")
    public ResponseEntity<Map<String, String>> csrf(
            HttpServletRequest request) {

        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "token", token.getToken()));
    }

    @PostMapping("/auth/login")
    public ResponseEntity<?> login(
            @Valid @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication verified;
        try {
            verified = authManager.authenticate(
                    UsernamePasswordAuthenticationToken
                            .unauthenticated(
                                    input.username(), input.password()));
        } catch (AuthenticationException failure) {
            // Public message does not distinguish nonexistent user,
            // wrong password, or account status. Never log secrets.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(Map.of("error", "invalid_credentials"));
        }

        // Build custom principal only after authentication. Demo has only alice.
        // Real apps look up id/tenant from a trusted account directory.
        if (!"alice".equals(verified.getName())) {
            throw new IllegalStateException(
                    "Authenticated account mapping unavailable");
        }

        AppPrincipal principal = new AppPrincipal(
                "user-100", "alice", "tenant-a");

        Authentication forSession =
                UsernamePasswordAuthenticationToken.authenticated(
                        principal, null, verified.getAuthorities());

        // Prevent session fixation and replace the old CSRF token.
        sessionStrategy.onAuthentication(
                forSession, request, response);

        // Spring Security 6: create a new context and SAVE it explicitly.
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(forSession);
        SecurityContextHolder.setContext(context);
        contextRepository.saveContext(context, request, response);

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(new UserView(
                        principal.userId(),
                        principal.username(),
                        principal.tenantId()));
    }

    @GetMapping("/me")
    public ResponseEntity<UserView> me(Authentication authentication) {
        AppPrincipal principal =
                (AppPrincipal) authentication.getPrincipal();

        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(new UserView(
                        principal.userId(),
                        principal.username(),
                        principal.tenantId()));
    }
}
```

**How it works:**

- `LoginRequest` holds only client-supplied username/password; **no role, tenant, or user ID from the client**. `@Valid` and `@NotBlank` reject blank input; production also needs body/request size limits at the reverse proxy and malformed JSON handling via a global error handler.
- `authManager.authenticate(...)` is where `DaoAuthenticationProvider` invokes the password encoder. Only when this succeeds is `AppPrincipal` constructed.
- `UsernamePasswordAuthenticationToken.authenticated(principal, null, authorities)` stores the principal **without a password** in the session; authorities come from the authentication provider, never from JSON input.
- `sessionStrategy.onAuthentication(...)` runs **before** `saveContext`, so the session ID is rotated before writing the authentication state.
- `SecurityContextHolder.createEmptyContext()` avoids mutating a shared existing context. `setContext` serves the remainder of the current request; `saveContext` persists it across requests.
- `/api/me` receives the `Authentication` populated by SecurityFilterChain. If not logged in, the request is rejected before reaching the controller.
- After login, the previous CSRF token is invalidated by `CsrfAuthenticationStrategy`; the client should fetch `/api/auth/csrf` again before its next state-changing request.
- `Map.of` and DTOs are serialized to JSON by Jackson; JSON property order is not guaranteed and should not be asserted by exact string matching in tests.

### Do Not Take This Shortcut

```java
// Wrong approach: only authenticating in the controller without saving the session.
Authentication a = authManager.authenticate(inputToken);
SecurityContextHolder.getContext().setAuthentication(a);
return ResponseEntity.ok("logged in");
```

This snippet assumes `authManager` and `inputToken` exist; it is not a standalone compilable program. On Spring Security 6 with explicit save, subsequent requests will not see the authentication, and the session fixation strategy will not have run.

## 10. Why Logout Should Use `LogoutFilter` Instead of Manually Deleting Cookies

When the frontend sends `POST /api/auth/logout`, Spring Security's `LogoutFilter` intercepts it before the MVC controller. With Section 8's config, the logout flow includes:

1. `CsrfFilter` validates the token for **POST**.
2. `LogoutFilter` matches the logout URL and HTTP method.
3. `SecurityContextLogoutHandler` clears authentication/context and invalidates the session as configured.
4. `CsrfLogoutHandler` removes the CSRF token associated with the logged-out session.
5. `JSESSIONID` cookie deletion is requested via `deleteCookies`.
6. `LogoutSuccessHandler` returns HTTP **204 No Content**, rather than redirecting to an HTML login page.

Do not write:

```java
@GetMapping("/api/auth/logout")
public void logout() {
    // Clearing only the client-side cookie does not revoke the server session.
}
```

A GET logout URL can be triggered by links, images, crawlers, or unintended navigation. With cookie-based authentication, using **POST with a CSRF token** prevents cross-site requests from forcing a user out. When SSO/OIDC or server-side refresh tokens are involved, logout also needs proper token revocation or front-channel/back-channel logout; clearing the Spring session **does not** log the user out of the external identity provider.

With a distributed session store, `invalidate()` must delete or invalidate the corresponding record. If a user has multiple sessions across devices, logging out on a laptop only invalidates that session unless a revoke-all policy exists.

## 11. Running the Example with Gradle and curl

From the project directory containing the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 11.1. Fetch the CSRF Token and Session Cookie

Use `curl` to save a cookie jar:

```bash
curl -i -c cookies.txt \
  http://127.0.0.1:8080/api/auth/csrf
```

Equivalent JSON response:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "<opaque-csrf-value>"
}
```

**`<opaque-csrf-value>` is an illustrative placeholder**, not a real token. Each GET may produce a different masked token value due to Spring Security 6 CSRF masking. Never hardcode an example token into later requests; use **the value returned by the server for this exact cookie-jar session**.

### 11.2. JSON Login with a Valid CSRF Token

Assume `CSRF_TOKEN` is set to the `token` field from the JSON response just received, and the cookie jar holds the session:

```bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -d '{"username":"alice","password":"demo-only"}' \
  http://127.0.0.1:8080/api/auth/login
```

Expect HTTP 200 with JSON equivalent to:

```json
{
  "userId": "user-100",
  "username": "alice",
  "tenantId": "tenant-a"
}
```

The session ID rotates upon successful login; `curl -c cookies.txt` updates the cookie jar. Password `demo-only` is test data for loopback only; never place real passwords in command history. Cookie jars hold sensitive data: restrict permissions and delete them after testing.

### 11.3. Call the API Using the Session

```bash
curl -i -b cookies.txt \
  http://127.0.0.1:8080/api/me
```

Expect HTTP 200 with `userId/username/tenantId` as above. Without a valid session cookie:

```bash
curl -i http://127.0.0.1:8080/api/me
```

Expect HTTP **401 Unauthorized** with the generic JSON body from the demo's `AuthenticationEntryPoint`. If the controller is still invoked with an invalid cookie, inspect `SecurityFilterChain` and the session repository.

### 11.4. Fetch a Fresh CSRF Token and POST Logout

Because successful login refreshes CSRF state, call again:

```bash
curl -i -b cookies.txt -c cookies.txt \
  http://127.0.0.1:8080/api/auth/csrf
```

Set `CSRF_TOKEN` to the **new** token, then run:

```bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -X POST http://127.0.0.1:8080/api/auth/logout
```

Expect **204 No Content**. After logout, verify the old session no longer grants access:

```bash
curl -i -b cookies.txt \
  http://127.0.0.1:8080/api/me
```

Expect **401**. Testing with a cookie jar may update/delete the cookie at logout; to verify server-side revocation, in a controlled operational test retain the **old session ID** in a secondary client and confirm it is no longer valid either. Never log or share session IDs externally.

### 11.5. Test the Error Branch

```bash
# Wrong password, but valid CSRF token:
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $CSRF_TOKEN" \
  -d '{"username":"alice","password":"wrong"}' \
  http://127.0.0.1:8080/api/auth/login
```

Expect a generic 401 when the CSRF token is valid. If you send an expired token or one tied to a different session, the request may be blocked with **403 by CSRF before the controller checks the password**. Thus diagnostics must distinguish CSRF failures from authentication failures instead of assuming every 403 means wrong password.

## 12. MockMvc Integration Test: Session Cookies, CSRF, and Logout

Create `src/test/java/demo/jsonsession/JsonSessionIntegrationTest.java`:

```java
package demo.jsonsession;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonSessionIntegrationTest {

    @Autowired
    MockMvc mvc;

    private record CsrfSession(MockHttpSession session, String token) {}

    private CsrfSession bootstrap() throws Exception {
        MvcResult response = mvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headerName")
                        .value("X-CSRF-TOKEN"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        String token = JsonPath.read(
                response.getResponse().getContentAsString(), "$.token");

        assertThat(session).isNotNull();
        assertThat(token).isNotBlank();
        return new CsrfSession(session, token);
    }

    private void login(CsrfSession csrf) throws Exception {
        mvc.perform(post("/api/auth/login")
                        .session(csrf.session())
                        .header("X-CSRF-TOKEN", csrf.token())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"demo-only"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId")
                        .value("user-100"))
                .andExpect(jsonPath("$.tenantId")
                        .value("tenant-a"));
    }

    @Test
    void anonymousCannotReadCurrentPrincipal() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"demo-only"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticateSession() throws Exception {
        CsrfSession csrf = bootstrap();

        mvc.perform(post("/api/auth/login")
                        .session(csrf.session())
                        .header("X-CSRF-TOKEN", csrf.token())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice","password":"wrong"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error")
                        .value("invalid_credentials"));

        mvc.perform(get("/api/me").session(csrf.session()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginRotatesIdAndPersistsCustomPrincipal() throws Exception {
        CsrfSession csrf = bootstrap();
        String oldId = csrf.session().getId();

        login(csrf);

        // Session fixation protection: old session ID rotates.
        assertThat(csrf.session().getId()).isNotEqualTo(oldId);

        mvc.perform(get("/api/me").session(csrf.session()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId")
                        .value("user-100"))
                .andExpect(jsonPath("$.username")
                        .value("alice"))
                .andExpect(jsonPath("$.tenantId")
                        .value("tenant-a"));

        // Another request without cookie does not inherit principal.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logoutMustHaveFreshCsrfAndInvalidatesSession()
            throws Exception {
        CsrfSession original = bootstrap();
        login(original);

        // Pre-login token was cleared by CsrfAuthenticationStrategy.
        mvc.perform(post("/api/auth/logout")
                        .session(original.session())
                        .header("X-CSRF-TOKEN", original.token()))
                .andExpect(status().isForbidden());

        // Fetch a fresh token from the authenticated post-login session.
        MvcResult fresh = mvc.perform(
                        get("/api/auth/csrf")
                                .session(original.session()))
                .andExpect(status().isOk())
                .andReturn();
        String freshToken = JsonPath.read(
                fresh.getResponse().getContentAsString(), "$.token");

        mvc.perform(post("/api/auth/logout")
                        .session(original.session())
                        .header("X-CSRF-TOKEN", freshToken))
                .andExpect(status().isNoContent());

        assertThat(original.session().isInvalid()).isTrue();

        // After logout, a new request is no longer authenticated.
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

These tests verify several key invariants:

1. Anonymous callers cannot read `/api/me`.
2. POST login missing a CSRF token is rejected **before verifying credentials**.
3. Wrong password with valid CSRF returns 401 and does not create an authenticated session.
4. Successful login rotates the session ID and saves the **custom principal** into the context.
5. A separate request without the session does not inherit authentication.
6. The pre-login CSRF token cannot be reused to log out after login.
7. POST logout with a fresh token returns 204, invalidates the session, and subsequent requests are unauthenticated.

`MockMvc` can verify `MockHttpSession` but does not prove cookie attributes in real browsers, HTTPS reverse proxies, load balancers, or distributed session stores. Additional E2E tests in the target environment are required.

Run:

```bash
./gradlew test
```

The example does not assert fixed Gradle stdout; the required outcome is **all JUnit/MockMvc tests passing**. On failure, inspect the HTTP status and test stack trace in a controlled environment—never disable CSRF or session fixation protection just to turn tests green.

## 13. Same-Origin JavaScript `fetch`: Never Keep Passwords in Storage

A same-origin frontend can use `fetch`:

```javascript
async function csrfToken() {
  const response = await fetch("/api/auth/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot get CSRF token");
  return response.json();
}

async function signIn(username, password) {
  const csrf = await csrfToken();
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });
  if (!response.ok) throw new Error("Login failed");
  return response.json();
}

async function signOut() {
  const csrf = await csrfToken();
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { [csrf.headerName]: csrf.token }
  });
  if (response.status !== 204) throw new Error("Logout failed");
}

// Login requires calling signIn(...) with user form input.
// After login completes, fetch a fresh CSRF token before mutating requests.
```

This is a **JavaScript module for a same-origin frontend**, not standalone Node code. The sample functions do not store passwords in `localStorage`, `sessionStorage`, or URLs. If the UI spans multiple tabs, tabs typically share the session cookie and must coordinate logout/rotation state together.

Not every cross-origin API should use `credentials: "include"`; allowing cross-site cookies requires analyzing SameSite, CSRF, CORS, and domains, and cannot be solved by setting `Access-Control-Allow-Origin: *` alongside credentials.

**CSRF tokens are session-bound data:** if you keep an old token after login/logout, the next POST request can fail with 403. Bootstrap a fresh token after authentication transitions, and handle CSRF expiration errors with a valid recovery flow rather than disabling validation.

## 14. `SecurityContextHolder` and Persisting Context Between Requests

In Spring Security 6, `SecurityContextHolderFilter` focuses on **loading** the context from the repository and leaves the application/filter responsible for **saving** when authentication changes explicitly. For a custom login:

```java
SecurityContext newContext =
        SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(authenticated);
SecurityContextHolder.setContext(newContext);
repository.saveContext(newContext, request, response);
```

This is a **snippet** assuming the variables already exist with the right types, not a standalone Java method.

Three distinct actions:

- `createEmptyContext()` ensures a fresh context, avoiding accidental mutation of an old shared context object.
- `setContext(...)` lets downstream logic within the current request read the authentication.
- `saveContext(...)` persists the context into the repository so the next request can use it.

`HttpSessionSecurityContextRepository` defaults to a Spring Security-managed attribute inside `HttpSession`; **do not call `session.setAttribute("user", ...)` and expect Spring Security to treat the session as authenticated**.

Never store an entire `Authentication` in a `static` field or global `ThreadLocal`. In a servlet server, worker threads in the pool are reused across different users; leaking `SecurityContextHolder` between requests can grant access to the wrong user.

When using multiple `SecurityFilterChain`s, the login endpoint and session-authenticated endpoints must share consistent chain/repository settings. A `STATELESS` chain covering `/api/**` can prevent the login session from being loaded later even if the controller called `saveContext`.

## 15. Session Fixation: Why Rotate the ID on Login?

**Session fixation** occurs when an attacker creates or knows an unauthenticated session ID and tricks the victim into continuing to use that same ID after logging in. Because the attacker already knows that ID, they can impersonate the victim if the session is upgraded without rotating its ID.

Example:

```text
Before login:
  JSESSIONID = SID-OLD    (unauthenticated)
                        |
                        v
Login succeeds:
  SessionAuthenticationStrategy rotates session ID
                        |
                        v
After login:
  JSESSIONID = SID-NEW    (holds SecurityContext)
```

`ChangeSessionIdAuthenticationStrategy` invokes the Servlet container's session ID rotation mechanism when an active session exists. Using `HttpSessionCsrfTokenRepository` causes GET CSRF to create an anonymous session, allowing tests to observe the session ID changing after login.

Rotating the ID **does not replace** `Secure`, `HttpOnly`, SameSite cookie controls, HTTPS, session expiration, and auditing. If a cookie is stolen after login, an attacker can still hijack the session; transport, browser, and server protections are also required.

If strict session concurrency rules are required, Spring Security offers concurrent session control strategies and `SessionRegistry`. A custom controller must ensure those strategies are actually invoked; `ChangeSessionIdAuthenticationStrategy` alone does not enforce "only one active device" or global logout.

## 16. CSRF for Both Login and Logout

A common mistake:

```java
http.csrf(csrf -> csrf.disable());
```

That disables CSRF for the entire chain, which is inappropriate for products **using browser auto-sent cookies** on side-effecting endpoints. Similarly, exempting `/api/auth/login` and `/api/auth/logout` without threat analysis can open **login CSRF** or **logout CSRF** vulnerabilities.

Why does login also need CSRF? Another website could submit a request forcing a victim's browser to log into an attacker-controlled account; the victim's subsequent actions then happen inside the wrong account. A CSRF token ensures the login flow was initiated within an authorized session/client.

Why does logout also need CSRF? A GET or unprotected POST logout request could be triggered cross-site, forcing unwanted logouts. Using HTTP POST alone **is not enough** against CSRF without tokens and appropriate origin policies.

Spring Security 6 can use **deferred CSRF tokens and BREACH masking** in request attributes. Thus the token returned by `getToken()` to the client may differ from the raw value stored in the session. The client must send **the exact value returned by the server**, without decoding or mutating it.

When authentication succeeds, `CsrfAuthenticationStrategy` rotates/clears the current token; on logout, `CsrfLogoutHandler` clears it as well. Requiring the frontend to bootstrap a new token after state transitions is by design.

## 17. Returning 401, 403, and Safe JSON Errors

In the demo:

| Scenario | Expected Status | Cause |
| --- | --- | --- |
| Anonymous `GET /api/me` | `401` | No authenticated session |
| POST login missing CSRF | `403` | `CsrfFilter` blocks before MVC controller |
| POST login valid CSRF, wrong password | `401` | `AuthenticationManager` rejects credentials |
| POST login valid | `200` | Session ID rotated and context saved |
| GET `/api/me` with valid session | `200` | Principal loaded from saved context |
| POST logout old or missing CSRF | `403` | Logout not executed |
| POST logout valid CSRF | `204` | Session invalidated |
| GET `/api/me` after logout | `401` | Authenticated session no longer exists |
| Logged-in user lacking resource permission | Typically `403` | Authorization failed, distinct from login failure |

Status codes form the contract of the demo configuration. A form-login system, API gateway, or custom handler may respond differently. **Never disclose in public responses** whether a username does not exist, an account is locked, the password specifically failed, or which tenant a user belongs to; the login example returns the same `invalid_credentials` for all `AuthenticationException` failures.

Infrastructure errors such as an unavailable database must be logged and classified internally rather than conflated with invalid user input. In production, a real outage can return a generic `503` without revealing provider internals, backed by correlation IDs and auditing.

Never log `@RequestBody LoginRequest` by calling `toString()`: default records include the password. The example overrides `toString()` to redact it, though request-body logging at reverse proxies, APMs, and controller interceptors must still be controlled.

## 18. Cookie Security: `HttpOnly`, `Secure`, `SameSite`, and HTTPS

`JSESSIONID` is a **cookie-based bearer credential**: anyone holding a valid cookie can use the server session unless additional safeguards exist.

Attributes:

- **`HttpOnly`**: JavaScript cannot read the cookie via standard `document.cookie`; does not prevent XSS from issuing same-origin requests itself.
- **`Secure`**: the browser sends the cookie only over HTTPS per policy (browser/localhost exceptions may differ). Production must use HTTPS.
- **`SameSite=Lax`**: limits certain cross-site cookie requests; does not replace CSRF tokens, especially with same-site cross-origin setups or edge cases.
- **`SameSite=Strict`**: stricter, though it can interfere with OAuth2 redirects or login links from external sites.
- **Domain/Path**: scopes where the cookie is sent; never widen the domain excessively just to share across many subdomains.

Production behind a trusted TLS proxy can configure:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  forward-headers-strategy: framework
```

This illustrates `application-prod.yml`; enable forwarded-header handling only if **the backend accepts traffic solely from designated reverse proxies** and the proxy sanitizes `Forwarded`/`X-Forwarded-*`. If the backend is directly reachable, clients can spoof HTTPS/host metadata. When deploying to production, configure `server.address` and network topology properly instead of leaving `127.0.0.1` when running in containers or separate hosts.

Never return `JSESSIONID` inside JSON for "the frontend to manage manually"; let the browser cookie jar enforce cookie policies. `HttpOnly` intentionally keeps JavaScript from reading the session credential.

## 19. Custom Principal Data, Stale Sessions, and Multi-Tenant Permissions

In the demo:

```text
AppPrincipal:
  userId   = user-100
  username = alice
  tenantId = tenant-a

Authentication authorities:
  ROLE_USER
```

The ID/tenant values are post-authentication data from a trusted account directory. In a multi-tenant application, services must still verify **resource ownership**—such as confirming a report belongs to `tenant-a`—rather than checking `ROLE_USER` alone.

An operational concern: the `SecurityContext` in a session can retain authorities/tenant **as of login time**, even after an admin disables the user or revokes permissions. Policies are needed for:

1. Session timeout and absolute max age.
2. Invalidating sessions when locking users, changing passwords, or resetting MFA as required by policy.
3. Revalidating sensitive permissions at data read/write time.
4. Considering `SessionRegistry` or a session store for per-user revocation.
5. Never letting `tenantId` in a request body override the actual tenant without verifying cross-tenant authorization.
6. With distributed sessions, testing version and serialization compatibility of `AppPrincipal`.

A JWT carrying claims shares the same staleness problem until expiration/revocation; sessions do not automatically solve every permission update.

## 20. Common Mistakes When Writing Custom JSON Login

| Symptom | Cause | Fix |
| --- | --- | --- |
| Login 200 but `/api/me` 401 | Only called `setContext` without `saveContext`, or chain is `STATELESS` | Use a consistent session repository and save context explicitly |
| Login 403 even with right password | Missing/mismatched CSRF token for the session | GET CSRF, send exact header, and preserve cookie |
| Logout 403 right after login | Pre-login CSRF token was reset | Bootstrap a fresh token from the authenticated session |
| User A and B contexts mix | Auth stored in static/ThreadLocal or shared session | Use per-session `SecurityContextRepository`, never globals |
| Session ID unchanged after login | Skipped `SessionAuthenticationStrategy` | Invoke change-session-ID strategy after auth success |
| Logout returns 204 yet session still works | Only deleted cookie or failed to invalidate server session | Use `LogoutFilter`/`SecurityContextLogoutHandler` and test invalidation |
| Login response leaks password/hash | Serialized raw `UserDetails` or request record | Return a minimal DTO and redact logs |
| Client claims `ROLE_ADMIN` | Trusted role field from JSON | Load authorities from trusted provider/account store |
| Cookie sent over HTTP | Missing HTTPS/`Secure` or misconfigured proxy | Enforce HSTS/TLS/Secure cookies and proper trust boundaries |
| Session lost across replicas | Local session storage while LB switches nodes | Use Spring Session/shared store or policy-backed sticky routing |
| UI fails to log out other tabs | Shared cookie/session while frontend keeps stale state | Recheck `/api/me` and broadcast logout across same-origin UI |
| Disabled user still active in old session | Sessions not revoked when user status changed | Implement session invalidation/revalidation per account lifecycle |
| Repeated brute-force login attempts | Missing rate limiting/account lockout/monitoring | Apply per-account/IP limits designed against DoS |
| Login fails on malformed JSON | Controller lacks validation/body error handling | Use `@Valid`, generic 400 responses, and body size limits |
| POST logout does not reach controller | LogoutFilter intercepts URL before MVC | This is intentional; test through the filter chain |
| CSRF still fails despite valid CORS | CORS does not replace CSRF | Keep session-bound tokens and configure origin policy properly |

### Debug in Order

1. Confirm the request matches the expected `SecurityFilterChain` and HTTP method.
2. Check whether POST login carries the session cookie and CSRF header from the GET bootstrap.
3. Verify which provider and password encoder `AuthenticationManager` actually uses.
4. Confirm the account directory resolved the principal ID/tenant.
5. Check whether the session fixation strategy actually rotated the ID.
6. Verify `HttpSessionSecurityContextRepository.saveContext` executed.
7. Check whether GET `/api/me` carries the new cookie and hits the same session repository.
8. Verify POST logout sends the **post-login** CSRF token and invalidates the session.
9. Inspect HTTPS, cookie path/domain/SameSite, and reverse proxy settings.
10. Verify session timeout, revocation, concurrent logins, and audit events.

## 21. Real-World Case: Session Concurrency and Multiple Devices

Suppose a user logs in on both a laptop and a phone; each device typically has its own session ID. Logging out on the laptop only invalidates the laptop's session unless a revoke-all mechanism exists; the phone session can remain active.

If **"only one session per user"** is required, Spring Security provides concurrent session controls, but a custom controller must integrate all pieces properly:

- `ConcurrentSessionControlAuthenticationStrategy`
- `RegisterSessionAuthenticationStrategy`
- `SessionRegistry` or a session tracking repository
- `ConcurrentSessionFilter` / integration supporting the session lifecycle

Do not merely register a `SessionRegistry` bean and assume old sessions expire automatically. Principal `equals`/`hashCode` semantics and distributed session storage also affect tracking. When a user is disabled, the app needs a policy to revoke all sessions by user ID rather than waiting for cookies to expire.

Using Spring Session with Redis/JDBC requires managing timeouts, cleanup, session ID rotation, serialization, GDPR/PII policies, and store operations. That is an **extension**, absent from this single-user single-process demo; never claim the demo is production-ready.

## 22. CORS and Same-Origin: Designing Cookie-Based APIs

A same-origin frontend calling:

```text
https://app.example.test/
https://app.example.test/api/auth/csrf
https://app.example.test/api/auth/login
https://app.example.test/api/me
https://app.example.test/api/auth/logout
```

has a far simpler cookie/CSRF model than a frontend on a different origin. Splitting the frontend to another domain requires explicit origin allowlists in CORS, proper `Access-Control-Allow-Credentials`, `SameSite=None; Secure` when genuinely cross-site, and careful CSRF evaluation.

**Never** set `Access-Control-Allow-Origin: *` with credentials and expect browsers to allow it. Nor should HTTP `Origin`/`Referer` or CORS be mistaken for authentication; browser policies do not stop attackers from sending requests with other tools.

Login/logout session APIs can still be CSRF targets even when every request uses JSON. Some cross-origin JSON requests trigger preflight, but **relying on preflight/CORS alone does not replace CSRF tokens** and breaks down across content types, variants, or proxies.

## 23. Tests to Add When Moving to Production

The demo MockMvc suite tests core invariants. A real system needs additional tests for:

1. **Nonexistent, locked, disabled, or password-expired accounts:** generic public response and no authenticated session created.
2. **Malformed JSON / oversized body / wrong content type:** returns 400/413/415 per contract with no stack traces.
3. **Brute force / rate limiting:** repeated failed logins are throttled and audit events never leak passwords.
4. **Session fixation in a real browser:** post-auth session ID differs from pre-auth, and cookie Path/Domain/Secure/HttpOnly/SameSite are accurate.
5. **Session timeout and logout:** an invalidated session ID cannot access endpoints even if the old cookie is replayed.
6. **Multi-tab login/logout races:** old CSRF tokens are not reused and contexts are not resurrected.
7. **Multi-tenant isolation:** users cannot access another tenant's resources by changing path IDs.
8. **Distributed sessions:** requests across replicas remain authenticated, revocations take effect, and contexts never leak.
9. **User disabled mid-session:** sessions are revoked/revalidated per real policy.
10. **XSS and CSRF:** HttpOnly session cookies do not stop XSS-driven requests; test CSP, output encoding, and anti-CSRF together.
11. **HTTPS / proxy:** no direct HTTP bypass, Secure cookies enforced, and redirects use the public host.
12. **Login/logout auditing:** logs include correlation ID and outcome/actor without secrets, CSRF tokens, or cookies.

A test using `.with(user("alice"))` only **pre-populates a principal**; it checks neither session persistence nor password verification. Use real JSON login requests as in Section 12 to test the actual flow.

## 24. Deployment Checklist

- SecurityFilterChain covers login, CSRF bootstrap, authenticated APIs, and logout with a fallback deny policy.
- JSON login actually invokes `AuthenticationManager` with a properly configured password encoder.
- Principal holds backend-verified identity data only, with no raw secrets.
- Login success triggers the session authentication strategy and rotates the session ID.
- CSRF token is issued for the right session, submitted on POST login/logout, and rotated after authentication.
- SecurityContext is created fresh, `setContext` is called, and `saveContext` persists it via the session repository.
- `/api/me` reads authentication from the stored SecurityContext rather than arbitrary custom session attributes.
- Logout goes through `LogoutFilter` via POST and invalidates the server-side session.
- `Secure`, `HttpOnly`, `SameSite`, domain/path, and HTTPS are configured properly for real browsers.
- Public errors are generic without disclosing user existence or leaking credentials.
- Rate limiting, session timeouts, revocation, and auditing match product requirements.
- Role/tenant authorization is enforced on the backend even when the session principal carries a tenant.
- MockMvc tests cover CSRF, wrong credentials, session fixation, session persistence, and logout.
- Across multiple replicas, an appropriate session store/consistency model and strategy are in place.
- With SSO/OIDC, application session logout and identity provider logout are designed separately.

## Key Takeaways

**Session-based JSON login in Spring Security Servlet** is not just parsing JSON and calling `AuthenticationManager.authenticate`. A secure flow must **verify credentials**, construct a **custom principal from trusted backend data**, **rotate the session ID**, **explicitly save `SecurityContext` into the session**, **keep CSRF enabled for login/logout**, and **invalidate the session on logout**. Return minimal JSON DTOs and protect `HttpOnly`/`Secure` cookies over HTTPS. For production, add account lifecycle management, concurrency/revocation, rate limiting, auditing, and real-browser E2E testing for cookies and proxies.