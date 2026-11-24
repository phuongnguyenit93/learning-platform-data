# Building a Session-Based JSON Login Endpoint and Persisting SecurityContext Properly

## 1. Objectives of This Capstone Practice

A Spring Boot application can use a traditional HTML login page, yet an SPA frontend or `fetch`-based client often prefers sending JSON:

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <token-issued-for-this-session>
Cookie: JSESSIONID=<session-id>

{"username":"learner","password":"correct-password"}
```

If the username/password are valid, the backend returns JSON and maintains a session. A subsequent request, such as `GET /api/auth/me`, must receive the same principal without asking for the password again.

**The crucial point in Spring Security 6.x:** when authenticating manually inside a **Spring MVC controller or custom filter**, merely calling `AuthenticationManager.authenticate(...)` and `SecurityContextHolder.setContext(...)` **is not enough to stay logged in across requests**. You must call `SecurityContextRepository.saveContext(context, request, response)` if you want the context restored from the HTTP session afterward.

This exercise belongs to the **Capstone Practical Exercises** in the **Spring Security - authentication** module. You will be able to:

1. Build proper JSON contracts for `POST /api/auth/login`, `GET /api/auth/me`, `GET /csrf`, and `POST /api/auth/logout`.
2. Configure `AuthenticationManager`/`DaoAuthenticationProvider` and `PasswordEncoder` explicitly rather than assuming the default `UsernamePasswordAuthenticationFilter` reads JSON.
3. Distinguish an **unauthenticated** Authentication token from an Authentication **verified by the provider**.
4. Create a new `SecurityContext`, set it on `SecurityContextHolder`, and **save it explicitly** with `HttpSessionSecurityContextRepository`.
5. Invoke `SessionAuthenticationStrategy` for **session fixation** protection and clear pre-login CSRF tokens after sign-in.
6. Retain CSRF protection for session-cookie-based JSON login/logout; fetch a token before login and a fresh token after login.
7. Use Spring Security's `LogoutFilter` to invalidate the session/clear context/clear CSRF and then return JSON.
8. Test the multi-request stateful flow with MockMvc and a shared cookie jar: anonymous, missing token, wrong credentials, valid login, persisted session, missing role, and logout.
9. Distinguish failure statuses `400/401/403`, session expiration, CORS, and reverse-proxy scenarios.
10. Identify parts of the demo that are insufficient for production: rate limiting, user store, multi-node sessions, auditing, TLS, validation, and secrets.

Scope is **Servlet/MVC, Java 17+, Spring Boot 3.5.16, and Spring Security 6.5.x**. Spring Boot 4/Spring Security 7 and WebFlux have several different APIs/configurations; always cross-check the docs for the exact version deployed.

## 2. Why Can't You Just Return JSON After Authenticate?

Consider incorrect code:

```java
@PostMapping("/api/auth/login")
public Map<String, Object> login(@RequestBody LoginRequest body) {
    Authentication accepted = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            body.username(), body.password()));

    SecurityContextHolder.getContext().setAuthentication(accepted);

    return Map.of("authenticated", true);
}
```

The first request may return `200 {"authenticated":true}`. However, when the browser sends `GET /api/auth/me` on **another request**, Spring Security reads the repository to obtain SecurityContext. Without saving:

```text
Request 1 POST /api/auth/login
  -> manager.authenticate(...) succeeds
  -> SecurityContextHolder now has principal
  -> controller returns 200
  -> DOES NOT call repository.saveContext(...)
  -> request finishes, thread-local context is cleared

Request 2 GET /api/auth/me
  -> SecurityContextHolderFilter loads context from repository
  -> repository has no saved authentication
  -> anonymous / 401
```

Spring Security 6.5 docs explicitly state that custom controllers/filters need `SecurityContextRepository` to persist context across requests. Never "fix" this by keeping a `static Authentication` in the JVM, disabling security filters, or setting a random `JSESSIONID` cookie manually.

**Correct approach:** after successful authentication, create a new `SecurityContext`, set the verified `Authentication`, set the context on the holder, and save it via the **same repository** configured on the Spring Security filter chain.

## 3. Distinguishing Five Key Components

| Component | Role | Does Not Replace |
| --- | --- | --- |
| `UsernamePasswordAuthenticationToken.unauthenticated(...)` | Wraps username/password into an authentication request | Does not prove the password is right |
| `AuthenticationManager.authenticate(...)` | Delegates to providers, returns valid Authentication or throws AuthenticationException | Does not define JSON responses |
| `SecurityContextHolder` | Holds Authentication for the current request/thread | Does not persist automatically across requests |
| `SecurityContextRepository` | Reads/writes SecurityContext across requests, e.g., via session | Does not verify passwords |
| `SessionAuthenticationStrategy` | Handles steps tied to a new login: session fixation, CSRF invalidation, session concurrency if configured | Does not replace AuthorizationManager |

At the HTTP layer there are also:

- `SecurityFilterChain`: enforces security filters, CSRF, and authorization.
- `SecurityContextHolderFilter`: in Spring Security 6, primarily **reads** the repository to restore SecurityContext. With custom authentication, you must save it.
- `HttpSessionSecurityContextRepository`: reads/writes context in HttpSession, typically under `SPRING_SECURITY_CONTEXT`.
- `CsrfFilter` and `CsrfTokenRepository`: validates unsafe methods like POST and stores CSRF tokens.
- `LogoutFilter` / `SecurityContextLogoutHandler` / `CsrfLogoutHandler`: cleans up session, context, and tokens on logout.
- `AuthenticationEntryPoint`: responds when an unauthenticated caller accesses a protected resource.
- `AccessDeniedHandler`: responds when an authenticated user lacks privileges, typically 403.

**A proper JSON login endpoint must not re-implement the entire SecurityFilterChain.** Put only authentication and context saving in the controller; let Spring filters enforce the surrounding protective layers.

## 4. Complete Request Flow with Session Cookies

```text
Browser                         Spring Security + MVC
   |                                      |
   | GET /csrf                            |
   |------------------------------------->|
   |                CsrfFilter exposes token;
   |                HttpSessionCsrfTokenRepository
   |                stores token with session
   |<------------- CSRF token + JSESSIONID --|
   |                                      |
   | POST /api/auth/login                 |
   | Cookie: JSESSIONID                  |
   | X-CSRF-TOKEN: <valid>                |
   | JSON username/password              |
   |------------------------------------->|
   |             CsrfFilter checks token |
   |             Controller parses JSON  |
   |             AuthenticationManager   |
   |             -> DaoAuthenticationProvider
   |             -> PasswordEncoder      |
   |             SessionAuthenticationStrategy:
   |               change session ID      |
   |               clear old CSRF token   |
   |             SecurityContext.createEmpty
   |             setAuthentication       |
   |             SecurityContextHolder.set
   |             repository.saveContext  |
   |<--------- 200 JSON + session cookie-|
   |                                      |
   | GET /api/auth/me                    |
   | Cookie: JSESSIONID (new)            |
   |------------------------------------->|
   |             SecurityContextHolderFilter
   |             repository loads context|
   |             AuthorizationFilter     |
   |<------------- 200 {"username":...}--|
   |                                      |
   | GET /csrf (new CSRF token)          |
   |<------------- new token ------------|
   |                                      |
   | POST /api/auth/logout + new CSRF    |
   |------------------------------------->|
   |             LogoutFilter clears session,
   |             SecurityContext + CSRF   |
   |<------------- 200 JSON -------------|
   |                                      |
   | GET /api/auth/me                    |
   |<------------- 401 ------------------|
```

In the **same-origin demo** below, browsers send same-origin cookies by default; with `fetch`, specify `credentials: "same-origin"` so the contract is explicit. For cross-origin frontends, configure `credentials: "include"`, a CORS allowlist supporting credentials, TLS, and proper SameSite/third-party cookie policies; CORS **does not replace authentication or CSRF**.

## 5. Designing the API Contract and Status Codes

| Request | Status | Sample Response | Condition |
| --- | --- | --- | --- |
| `GET /csrf` | 200 | JSON `token/headerName/parameterName` | Anonymous allowed, creates/retrieves session CSRF |
| `POST /api/auth/login` | 200 | `{"username":"learner","authenticated":true}` | Valid JSON, valid CSRF, right password |
| `POST /api/auth/login` | 400 | `{"code":"invalid_request",...}` | Blank username/password (controller validation) or malformed JSON |
| `POST /api/auth/login` | 401 | `{"code":"invalid_credentials",...}` | Provider rejects credentials; intentionally generic response |
| `POST /api/auth/login` | 403 | CSRF filter response | Missing/invalid CSRF token, **never reaches controller** |
| `GET /api/auth/me` | 200 | User JSON | Session holds valid SecurityContext |
| `GET /api/auth/me` | 401 | May have empty body in demo | Not logged in or session expired |
| `GET /api/admin` | 403 | Access denied response | User has `ROLE_USER` but lacks `ROLE_ADMIN` |
| `POST /api/auth/logout` | 200 | `{"status":"logged_out"}` | Valid CSRF token, logout filter cleanup |
| `POST /api/auth/logout` | 403 | CSRF rejection | Missing/invalid CSRF token |

HTTP status alone is not the full proof. Login failures come from the controller/authentication manager; CSRF 403 occurs **before the controller**; protected GET 401 comes from the entry point; insufficient privilege 403 comes from authorization. With default `formLogin`, many cases redirect to HTML login instead of JSON, so the demo **disables formLogin and httpBasic** to keep the API contract clean.

**Never return passwords, raw `AuthenticationException.getMessage()`, session IDs, or CSRF tokens in a successful login response.** CSRF tokens are served by a dedicated endpoint with `Cache-Control: no-store`.

## 6. Runnable Project Structure

```text
json-session-login-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jsonlogin/JsonSessionLoginApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/jsonlogin/JsonSessionLoginApplicationTests.java
```

This is a complete Servlet/MVC project for hands-on practice. There is no production database or IdP; it uses an in-memory user with a **synthetic password supplied via the environment**. Because authentication runs through real Spring Security providers, the code validates context persistence across sessions.

### 6.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>json-session-login-demo</artifactId>
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

**Dependency note:** `spring-boot-starter-security` brings in `spring-security-web`, `spring-security-config`, and password/provider APIs; no extra dependency is needed for `SecurityContextRepository`. `spring-security-test` supplies test request post-processors, while `starter-test` supplies JUnit/MockMvc/JSON testing.

### 6.2. application.yml

```yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax

app:
  demo:
    login-password: "${DEMO_LOGIN_PASSWORD}"
```

No hardcoded default password is present. `SameSite=Lax` is only a cookie-level mitigation and **does not replace CSRF tokens**. In HTTPS production deployments, session cookies require `Secure`, trusted proxy forwarded-header config, and HSTS; the local HTTP demo omits mandatory `Secure` so lab browsers still work.

**Important:** if running the frontend on a different origin (especially cross-site), SameSite/third-party cookie rules may stop sessions from being sent. This guide uses **same-origin** as the baseline to isolate SecurityContext persistence, then covers cross-origin extensions in a dedicated section.

## 7. Core Java Code: SecurityFilterChain + AuthenticationManager + Repository

Create **a single file** `src/main/java/demo/jsonlogin/JsonSessionLoginApplication.java`:

```java
package demo.jsonlogin;

import java.nio.charset.StandardCharsets;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonSessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonSessionLoginApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.login-password}") String password) {

        // Synthetic secret for local lab only, never for production.
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "DEMO_LOGIN_PASSWORD must be set and sufficiently long");
        }

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {

        // Provider that actually verifies passwords via PasswordEncoder.
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        // The controller below uses this exact manager.
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Reads and writes context in HttpSession.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        // Expected token stored in session; X-CSRF-TOKEN sent by client.
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy loginSessionStrategy(
            CsrfTokenRepository csrfRepository) {

        // In Spring Security 6, custom MVC logins must invoke
        // the session strategy directly; SessionManagementFilter
        // does not detect a manual login automatically by default.
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(csrfRepository)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfRepository) throws Exception {

        return http
            .securityContext(context -> context
                .securityContextRepository(contextRepository))

            // This is a session-backed API; do not set STATELESS.
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.IF_REQUIRED))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/csrf").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/auth/me").authenticated()
                .requestMatchers(HttpMethod.GET,
                    "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll())

            // POST login and POST logout still require a CSRF token.
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfRepository))

            // Disable form processing filter / HTML redirect
            // since the controller handles JSON POST /api/auth/login.
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)

            // Protected GET anonymous -> 401 (no redirect).
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))

            // Use standard LogoutFilter to clean up context/session/CSRF.
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                    response.setHeader("Cache-Control", "no-store");
                    response.getWriter().write(
                        "{\"status\":\"logged_out\"}");
                })
                .permitAll())
            .build();
    }
}

record LoginRequest(String username, String password) {}

record LoginResult(String username, boolean authenticated) {}

record ErrorBody(String code, String message) {}

@RestController
class AuthController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository contextRepository;
    private final SessionAuthenticationStrategy sessionStrategy;

    AuthController(
            AuthenticationManager manager,
            SecurityContextRepository contextRepository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.contextRepository = contextRepository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping(value = "/", produces = MediaType.APPLICATION_JSON_VALUE)
    java.util.Map<String, String> index() {
        return java.util.Map.of(
            "csrf", "/csrf",
            "login", "/api/auth/login",
            "me", "/api/auth/me",
            "logout", "/api/auth/logout");
    }

    @GetMapping(value = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<CsrfToken> csrf(CsrfToken token) {
        // Access token value so deferred token is loaded/stored.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(token);
    }

    @PostMapping(value = "/api/auth/login",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (body == null || body.username() == null
                || body.username().isBlank()
                || body.password() == null
                || body.password().isBlank()) {
            return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .body(new ErrorBody(
                    "invalid_request", "Username and password required"));
        }

        try {
            // 1. Unauthenticated: do not call authenticated factory
            //    or setAuthenticated(true) using client-supplied data.
            UsernamePasswordAuthenticationToken candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password());

            // 2. Provider verifies password and account status.
            Authentication accepted = manager.authenticate(candidate);

            // 3. Session fixation: rotate session ID.
            //    CSRF strategy: clear pre-login token; GET /csrf
            //    on a subsequent request generates a fresh token.
            sessionStrategy.onAuthentication(
                accepted, request, response);

            // 4. Create a fresh context; do not mutate a global singleton.
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(accepted);
            SecurityContextHolder.setContext(context);

            // 5. REQUIRED for custom session-backed JSON login.
            //    This same repository is used by the filter chain.
            contextRepository.saveContext(context, request, response);

            // 6. Return public data only, never credentials.
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginResult(accepted.getName(), true));

        } catch (AuthenticationException rejected) {
            // Do not return rejected.getMessage() or specific
            // locked/user-not-found types to public callers.
            SecurityContextHolder.clearContext();

            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(new ErrorBody(
                    "invalid_credentials", "Sign-in failed"));
        }
    }

    @GetMapping(value = "/api/auth/me",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<LoginResult> currentUser(Authentication authentication) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new LoginResult(
                authentication.getName(), authentication.isAuthenticated()));
    }
}
```

### 7.1. Step-by-Step Code Walkthrough

**A — `AuthenticationManager` and provider:**

`new ProviderManager(List.of(provider))` wraps a `DaoAuthenticationProvider` using `UserDetailsService` and BCrypt. The controller simply calls `manager.authenticate(candidate)`. On invalid passwords, the manager throws `AuthenticationException`; the controller returns a generic 401. Never use a username string or `Origin` header as proof that a user is logged in.

**B — `HttpSessionSecurityContextRepository`:**

This repository is **shared** between `SecurityFilterChain` and the controller. Creating a separate repository in the controller or configuring a stateless chain would prevent subsequent requests from loading saved state. In this project, both receive the exact same Spring bean.

**C — Explicit Invocation of `SessionAuthenticationStrategy`:**

Spring Security 6 does not use `SessionManagementFilter` by default to detect a new `Authentication` set manually by a controller. Therefore, the controller calls `CompositeSessionAuthenticationStrategy` **before `saveContext`**, combining:
- `ChangeSessionIdAuthenticationStrategy`: rotates the session ID if a session already exists, mitigating session fixation.
- `CsrfAuthenticationStrategy`: clears the CSRF token used prior to authentication; subsequent requests require a fresh token.

Production systems may also require a concurrent-session registry, `maximumSessions`, event publishers, MFA reauthentication, and remember-me logic; none of those are **automatically wired merely because a controller calls `authenticate`**.

**D — Creating and Saving `SecurityContext`:**

`SecurityContextHolder.createEmptyContext()` prevents sharing a mutable context across requests/threads. `setAuthentication(accepted)` attaches the provider-verified object. `SecurityContextHolder.setContext(context)` makes the principal visible to controllers/services within the same request; **`saveContext`** makes subsequent requests read it back from HttpSession.

**E — Using `LogoutFilter` Instead of Clearing a Few Variables Manually:**

Standard Spring Security logout already coordinates `SecurityContextLogoutHandler` and `CsrfLogoutHandler`. It handles session invalidation, context cleanup, and CSRF token clearing; we only customize the success response to return JSON. Writing `@PostMapping("/api/auth/logout")` manually and only calling `SecurityContextHolder.clearContext()` can leave the Authentication inside the repository so subsequent requests remain logged in.

**F — CSRF Remains Enabled by Default:**

`.csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))` still blocks POST requests lacking a token. Never add `csrf.disable()` just to "make JSON login testing easier"; doing so leaves browsers holding session cookies vulnerable to unwanted state-changing requests.

### 7.2. Why Not Annotate Login with `@Transactional`?

Authentication and HttpSession persistence do not inherently form a single JDBC transaction. If you write audits, login counters, refresh tokens, or tenant state, define explicit transaction boundaries and rollback rules. Do not equate `saveContext` into HttpSession with committing business data; when using a distributed session store, you also face cache/network consistency characteristics.

### 7.3. What Happens on Authentication Failure?

The controller catches `AuthenticationException` and returns a generic message. Never tell callers "username does not exist" or "account is locked", as that aids user enumeration. In production, you **must** internally distinguish `BadCredentialsException` from `AuthenticationServiceException` (system outage), track errors, apply rate limits, and avoid turning DB/LDAP outages into prolonged "wrong password" errors. This example keeps the public response simple to stay focused on session persistence.

## 8. Using Fetch Properly with Cookies and CSRF

The snippets below assume the frontend is **same-origin** with the backend (e.g., pages served from `http://localhost:8080`). Cross-origin setup is covered in Section 15.

### 8.1. Obtaining the Initial Token

```javascript
const BASE = ""; // same origin

async function obtainCsrfToken() {
  const response = await fetch(BASE + "/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Cannot obtain CSRF token");
  }
  return response.json(); // { token, headerName, parameterName }
}
```

`GET /csrf` may create an HttpSession to hold the expected CSRF token. The browser receives the session cookie; the subsequent **POST must send that same cookie** without creating a new jar between the two requests.

### 8.2. Logging In with JSON

```javascript
async function jsonLogin(username, password) {
  const csrf = await obtainCsrfToken();

  const response = await fetch(BASE + "/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });

  const data = await response.json();

  if (!response.ok) {
    // Do not log passwords or tokens.
    throw new Error(data.code || "login_failed");
  }

  // Session is stored on the server. Browser retains the cookie automatically.
  // Login cleared the old CSRF token; fetch a fresh token for later requests.
  await obtainCsrfToken();

  return data; // {username:"learner",authenticated:true}
}
```

**Do not treat HTTP 200 alone as proof of successful login in every app.** Here the JSON contract returns `authenticated:true` because the controller only emits it after the manager verifies credentials and saves the context. If you accidentally leave default `formLogin` enabled, `fetch` can follow a redirect to an HTML login page and end up with a 200 unrelated to login success.

### 8.3. Verifying the New Session on Another Request

```javascript
async function currentUser() {
  const response = await fetch(BASE + "/api/auth/me", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Unexpected response " + response.status);
  }
  return response.json();
}
```

The browser **does not need to resend username/password**. It sends the session cookie; Spring's `SecurityContextHolderFilter` reads `Authentication` from the session repository. Also never store `Authentication` in `localStorage` as "login proof" in place of the server: `localStorage` is JS-writable and is never trusted by Spring Security.

### 8.4. Logging Out via Spring Security

```javascript
async function jsonLogout() {
  const csrf = await obtainCsrfToken();

  const response = await fetch(BASE + "/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrf.headerName]: csrf.token
    }
  });

  if (!response.ok) {
    throw new Error("Logout rejected " + response.status);
  }

  return response.json(); // {status:"logged_out"}
}
```

Logout **must not use GET for convenience**. With CSRF protection enabled, POST logout requires a valid CSRF token. After logout, the frontend should clear client-side state and avoid reusing old tokens or sessions.

### 8.5. Where Never to Store Tokens

- Never put passwords, raw session IDs, or CSRF tokens in URL query strings.
- Never log full request/response bodies on login/logout endpoints.
- Never store username/password in the frontend to replay automatically forever.
- Do not send JWTs in this example: this is session-cookie authentication, not a JWT resource server.
- A CSRF token is not a "bearer access token". It prevents forged unsafe methods within a session context and is never proof that a user is logged in.

## 9. Testing with curl: One Cookie Jar from Start to Finish

Start the local server:

```bash
export DEMO_LOGIN_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

Another shell session can use `curl` to verify each step. With `curl`, **the cookie jar must be preserved**. To extract JSON automatically, use a tool with a JSON parser; the steps below show the manual sequence so no fake token value is hardcoded.

### Step 1: GET /csrf, Save the Cookie

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

Expected response:

```json
{
  "parameterName": "_csrf",
  "token": "<generated-CSRF-token>",
  "headerName": "X-CSRF-TOKEN"
}
```

**This structure is illustrative; the real token is randomly generated by the server and must be read from the matching session's response.** The cookie jar contains the session identifier; protect that file and never commit it.

### Step 2: POST JSON Login with Cookie and Token

```bash
# Replace <csrf-from-step-1> with the token returned from step 1.
# Never put real production passwords into shell history.
curl -i -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <csrf-from-step-1>' \
  --data '{"username":"learner","password":"<local-lab-password>"}'
```

**Note on command placeholders:** the two `<...>` values are placeholders, not literal values to run verbatim. When practicing in a safe environment, use your provisioned lab secret and real session token/cookie; avoid pasting passwords into shell history by using scripts reading from a secret store or session variable. The JSON literal is shown to illustrate the protocol, not as copy-paste automation.

Expected: `200 {"username":"learner","authenticated":true}`; the session cookie ID may rotate in the response. The cookie jar must retain the **latest** value rather than pinning the pre-login ID.

### Step 3: GET /api/auth/me with Only the Cookie

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/me
```

If SecurityContext was saved properly, expect 200 JSON with user `learner`, without sending the password. If 401, check troubleshooting: did the request send the new cookie, did the repository save the context, was the session invalidated, or is the chain configured as stateless?

### Step 4: GET a Fresh /csrf, Then POST Logout

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

Record the **new token**. Then:

```bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/api/auth/logout \
  -H 'X-CSRF-TOKEN: <new-CSRF-token>'
```

Expected 200 `{"status":"logged_out"}`. A subsequent `GET /api/auth/me` must no longer be authenticated. Use a separate cookie jar per scenario/test so sessions never mix.

**Never run `curl -v` or save request dumps containing raw passwords, sessions, or CSRF tokens into shared logs.**

## 10. MockMvc: Verifying Stateful Login Across Multiple Requests

This is the most important part to ensure the exercise doesn't stop at "returns 200". We must reuse **the same `MockHttpSession`** from fetching the CSRF token through checking subsequent requests.

File: `src/test/java/demo/jsonlogin/JsonSessionLoginApplicationTests.java`

```java
package demo.jsonlogin;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
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

@SpringBootTest(properties = {
    "app.demo.login-password=synthetic-test-password-only-123456"
})
@AutoConfigureMockMvc
class JsonSessionLoginApplicationTests {

    private static final String PASSWORD =
        "synthetic-test-password-only-123456";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    record SessionCsrf(
        MockHttpSession session,
        String headerName,
        String token) {}

    private SessionCsrf getCsrf(MockHttpSession existing)
            throws Exception {
        var builder = get("/csrf");
        if (existing != null) {
            builder.session(existing);
        }

        MvcResult result = mvc.perform(builder)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token").isString())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        JsonNode json = mapper.readTree(
            result.getResponse().getContentAsString());

        return new SessionCsrf(
            session,
            json.get("headerName").asText(),
            json.get("token").asText());
    }

    private MvcResult login(SessionCsrf csrf, String password)
            throws Exception {
        String json = mapper.writeValueAsString(
            new LoginRequest("learner", password));

        return mvc.perform(post("/api/auth/login")
                .session(csrf.session())
                .header(csrf.headerName(), csrf.token())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andReturn();
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/auth/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfIs403BeforePasswordIsChecked()
            throws Exception {
        mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"learner\","
                    + "\"password\":\"" + PASSWORD + "\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordReturnsGeneric401() throws Exception {
        SessionCsrf csrf = getCsrf(null);

        MvcResult response = login(csrf, "incorrect");

        assertThat(response.getResponse().getStatus())
            .isEqualTo(401);
        assertThat(response.getResponse().getContentAsString())
            .contains("invalid_credentials")
            .doesNotContain("BadCredentialsException");

        mvc.perform(get("/api/auth/me")
                .session(csrf.session()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void successfulJsonLoginPersistsAcrossSecondRequest()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);

        MvcResult success = login(csrf, PASSWORD);
        assertThat(success.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession loggedIn = (MockHttpSession)
            success.getRequest().getSession(false);

        assertThat(loggedIn).isNotNull();

        mvc.perform(get("/api/auth/me")
                .session(loggedIn))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true));

        // Same session, third request remains authenticated.
        mvc.perform(get("/api/auth/me")
                .session(loggedIn))
            .andExpect(status().isOk());
    }

    @Test
    void successfulLoginChangesSessionId() throws Exception {
        SessionCsrf csrf = getCsrf(null);
        String beforeId = csrf.session().getId();

        MvcResult response = login(csrf, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession after = (MockHttpSession)
            response.getRequest().getSession(false);

        assertThat(after).isNotNull();
        assertThat(after.getId()).isNotEqualTo(beforeId);
    }

    @Test
    void stalePreLoginCsrfTokenIsNotReusableAfterLogin()
            throws Exception {
        SessionCsrf first = getCsrf(null);

        MvcResult response = login(first, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession session = (MockHttpSession)
            response.getRequest().getSession(false);

        // Login strategy cleared the old CSRF token.
        mvc.perform(post("/api/auth/logout")
                .session(session)
                .header(first.headerName(), first.token()))
            .andExpect(status().isForbidden());

        // Obtain a fresh token before logging out.
        SessionCsrf second = getCsrf(session);
        assertThat(second.token()).isNotEmpty();

        mvc.perform(post("/api/auth/logout")
                .session(session)
                .header(second.headerName(), second.token()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("logged_out"));
    }

    @Test
    void loggedInUserCannotUseAdminEndpoint()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);
        MvcResult response = login(csrf, PASSWORD);
        assertThat(response.getResponse().getStatus()).isEqualTo(200);

        MockHttpSession loggedIn = (MockHttpSession)
            response.getRequest().getSession(false);

        mvc.perform(get("/api/admin")
                .session(loggedIn))
            .andExpect(status().isForbidden());
    }

    @Test
    void blankPasswordIs400WhenCsrfIsValid()
            throws Exception {
        SessionCsrf csrf = getCsrf(null);

        mvc.perform(post("/api/auth/login")
                .session(csrf.session())
                .header(csrf.headerName(), csrf.token())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"learner\",\"password\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("invalid_request"));
    }
}
```

Run:

```bash
mvn test
```

**Expect 8 passing tests** on a machine with Java 17+, Maven, and dependency access. This expectation is by design, **not a report of an executed Maven run**. The test suite verifies:

- Protected GET without a session → 401.
- POST login missing CSRF → 403 before the controller.
- Wrong password login → generic 401 JSON, no authenticated access granted.
- Valid login → 200, subsequent request needs only the same session.
- Login rotates the session ID to mitigate session fixation.
- Pre-login CSRF token cannot be reused for POST logout after login.
- Authenticated user lacking ADMIN role → 403.
- JSON body missing a valid password → 400.

**Note on MockMvc/concurrency:** each test method uses its own session; avoid parallel tests sharing unisolated state. `MockMvc` does not prove browser cookie policies, reverse proxy/session affinity, or real multi-node stores. Add embedded-server and browser integration tests for those concerns.

## 11. Why Must SessionAuthenticationStrategy Be Called Before saveContext?

A standard login filter like `UsernamePasswordAuthenticationFilter` performs several steps after provider success:

1. Run `SessionAuthenticationStrategy`.
2. Create and save SecurityContext.
3. Execute remember-me success handling if configured.
4. Publish interactive authentication events.
5. Invoke `AuthenticationSuccessHandler`.
6. Finish the request with an appropriate redirect or response.

An MVC login controller **is not exempt** from these essential session-security steps. Omitting `SessionAuthenticationStrategy` can leave you without session fixation protection; omitting `saveContext` loses auth on the next request; mishandling logout leaves the session authenticated.

In our example:

```java
Authentication accepted = manager.authenticate(candidate);

sessionStrategy.onAuthentication(accepted, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(accepted);
SecurityContextHolder.setContext(context);
contextRepository.saveContext(context, request, response);
```

**Order matters:** call the session strategy only after the provider succeeds; rotate the session ID and clear the old CSRF token before saving the context; then return JSON. Never use `session.getId()` as user proof or manually set arbitrary session attributes in place of the Spring Security repository.

### 11.1. Session Fixation and request.setSessionId

Session fixation occurs when an attacker tricks a victim into using a session ID known to the attacker, and the ID does not change when the victim logs in, allowing session hijacking. `ChangeSessionIdAuthenticationStrategy` invokes Servlet's `HttpServletRequest.changeSessionId()` when a session exists; on modern Servlet containers, this is Spring Security's default choice.

Never craft `Set-Cookie: JSESSIONID=<random string>` manually. Let the container manage session IDs, cookie `Path`, `HttpOnly`, `Secure`, `SameSite`, and the backing store.

### 11.2. Session Concurrency

If the product limits each user to one active session, Spring provides `maximumSessions(1)`/`SessionRegistry`. However, **a custom-written controller must explicitly integrate the concurrent session strategy** and registry lifecycle; merely adding a DSL line does not automatically limit custom controllers. Test with two browser sessions and multiple nodes.

### 11.3. SecurityContextHolderStrategy

The example uses static `SecurityContextHolder`, which suffices for single-ApplicationContext apps. Spring Security also allows injecting `SecurityContextHolderStrategy` to avoid strategy configuration races in multi-context setups. Never store `SecurityContext` in mutable singletons or pass ThreadLocals to async worker threads without context propagation.

## 12. CsrfTokenRepository: Pre-Login vs. Post-Login Tokens

In Spring Security 6, CSRF protection is enabled by default for unsafe methods, with **deferred loading** and **BREACH protection** (tokens are randomly masked per request). Thus, comparing two token strings across two GETs does not tell you whether the underlying persisted token rotated; the two strings differ due to masking even when the repository token stays the same.

**The bigger takeaway:** `CsrfAuthenticationStrategy` removes the old token from the repository upon login. Afterward, the frontend must GET a fresh `/csrf` token; any POST using the pre-login token must be rejected.

### 12.1. Why Can GET /csrf Create an HttpSession?

`HttpSessionCsrfTokenRepository` needs somewhere to store the expected token to verify POSTs. When the controller accesses `CsrfToken.token` to render JSON, the deferred token may be generated/loaded and persisted in HttpSession. This creates a session **before the user signs in**, which is completely normal: having a session ID **does not mean authenticated**.

### 12.2. XorCsrfTokenRequestAttributeHandler and SPAs

Per Spring Security 6.5, the default request attribute handler is `XorCsrfTokenRequestAttributeHandler` for BREACH protection, and `HttpSessionCsrfTokenRepository` is the default repository. When returning the token via `/csrf`, frontend code uses the returned value and header name directly. If a frontend reads an unmasked token directly from `CookieCsrfTokenRepository`, configure the SPA request handler per official docs rather than sending an unmasked token to a handler expecting a masked token.

This exercise **does not use `CookieCsrfTokenRepository`**; the token is delivered in JSON and the expected token stays in the session, with no separate `XSRF-TOKEN` cookie.

### 12.3. Why Not Disable CSRF to Make POST Login Easier?

In session-backed browser apps, cookies are attached automatically by the browser per cookie policy. Attackers can exploit login CSRF, session swapping, or unwanted state changes if protection is missing. CSRF and session auth answer two different questions:
- Session: which user's authenticated session is the client presenting?
- CSRF: did this unsafe request originate with a valid token/intent?

A successful CORS preflight **does not** replace CSRF tokens, even for JSON frontends. `SameSite` cookies mitigate some cross-site risks but do not replace server-side checks in cookie-based threat models.

## 13. Common Mistakes When Writing Custom JSON Login

### 13.1. Failing to Call saveContext

**Wrong:**

```java
SecurityContextHolder.setContext(context);
return ResponseEntity.ok(Map.of("authenticated", true));
```

**Right:** call `contextRepository.saveContext(context, request, response)` before the response commits. Always use the **same repository bean** registered on the security filter chain.

### 13.2. Setting Authentication on the Existing Context Only

```java
SecurityContextHolder.getContext()
    .setAuthentication(authenticated);
```

This does not persist across requests. Because mutable contexts can be shared by reference, Spring Security recommends `createEmptyContext()` and setting it to avoid races/shared mutations. Use the accepted `Authentication` from the manager, never calling `setAuthenticated(true)` on a client-supplied token.

### 13.3. Setting SessionCreationPolicy.STATELESS

```java
http.sessionManagement(s ->
    s.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

This policy fits certain bearer/API-key architectures, yet **contradicts** keeping login state via HttpSession. You can deliberately configure another repository or multiple chains, but never copy stateless configs from a resource-server tutorial into a session-login chain and expect `JSESSIONID` to work.

### 13.4. Returning 200 on Wrong Password

Critical bug:

```java
try {
    manager.authenticate(candidate);
} catch (AuthenticationException ex) {
    // WRONG: merely logs a warning and proceeds to create an authenticated session
}
return ResponseEntity.ok(Map.of("authenticated", true));
```

If the manager rejects, halt the success branch and never save an authenticated context. Keep public responses generic against enumeration; internal telemetry should distinguish credential failures from infrastructure outages.

### 13.5. POST /login Returns 403 and You Blame the Password

Without a CSRF token, `CsrfFilter` rejects **before the controller runs**. Fetch `GET /csrf`, keep the same cookie jar, and send the proper header. Do not modify `AuthenticationManager` when the failure is CSRF.

### 13.6. Login Succeeds Yet /me Still Returns 401

Common causes: forgot `saveContext`, controller and chain use different repositories, new cookie was not sent, session dropped at the load balancer, session store is not shared, session timed out, or the new client request omitted `credentials`.

### 13.7. Logout Calls Only SecurityContextHolder.clearContext()

Clearing the holder on the current thread does not necessarily delete the `Authentication` saved in the session repository. Use `LogoutFilter`, which handles invalidation, context persistence, CSRF, and other `LogoutHandler` instances.

### 13.8. Sending Raw Passwords in URLs

Never send `GET /api/auth/login?username=...&password=...`; URLs end up in browser history, reverse proxy logs, analytics, referrers, and caches. Use a POST JSON body over HTTPS and avoid logging request bodies.

### 13.9. Trusting Cookie IDs as User IDs

A session/cookie ID is an opaque session credential. Never turn client-supplied `userId`, `role`, or `X-User` headers into an `Authentication` without a trusted pre-auth gateway and verification boundary. Principals and roles must come from trusted providers/stores.

### 13.10. HTTP Basic or formLogin Unexpectedly Intercepting the Endpoint

If `formLogin` is enabled alongside a `POST /login` controller, `UsernamePasswordAuthenticationFilter` may intercept requests before MVC (depending on matchers) and trigger redirects. This exercise uses a dedicated `/api/auth/login` path and disables `formLogin/httpBasic` for consistent results.

## 14. Cookie, TLS, and Session Lifetime Configuration

A production session-based web app should apply:

- HTTPS and HSTS; never send session cookies or passwords over public HTTP.
- `HttpOnly` session cookies to reduce direct JS access to cookies.
- `Secure` cookies for HTTPS; reverse proxies must forward trusted scheme headers.
- `SameSite=Lax/Strict/None` matching frontend/backend architecture. `None` typically requires `Secure` and remains subject to third-party cookie policies.
- Host-only cookies where possible, avoiding overly broad `Domain` attributes; consider the `__Host-` prefix if infrastructure supports it.
- Never pass session IDs via URL rewriting or logs.
- Session idle timeouts and absolute timeouts/reauthentication for sensitive actions.
- Invalidate and purge state on logout; avoid retaining stale sessions in frontend caches.
- Session fixation protection on login, plus step-up/MFA policies where business risk demands.
- Manage concurrent sessions, revocation on password resets, and role changes.
- Use a shared/distributed session repository backing store across multiple pods/instances.

**Note:** `server.servlet.session.cookie.secure=true` behaves differently on localhost HTTP tests; enable it explicitly where HTTPS exists, and never deploy insecure dev settings to the public Internet.

## 15. Cross-Origin Frontends: CORS, Credentials, and Cookie Policies

Example:

```text
Frontend: https://app.example.com
Backend:  https://api.example.com
```

These two hosts are **cross-origin**, yet typically **same-site** when both use HTTPS under the same registrable domain. For browser JS to read backend responses, configure an explicit CORS allowlist, and credentialed requests require:

```javascript
fetch("https://api.example.com/api/auth/me", {
  credentials: "include"
});
```

The backend must emit exact CORS headers for the frontend origin; never use `Access-Control-Allow-Origin: *` with credentials. Configure `Access-Control-Allow-Credentials: true`, allowed methods/headers covering `Content-Type` and `X-CSRF-TOKEN`, and handle `OPTIONS` preflight before Spring authentication.

**CORS neither authenticates identity nor prevents CSRF.** A 200 preflight only satisfies browser cross-origin policy; it never means the user is logged in. A browser may block JS from reading a response while still letting the server execute a simple request; therefore, session-based mutations must still verify CSRF.

If frontend and API live on **different sites**, `SameSite` and third-party cookie blocking can make session cookies unreliable. Consider a same-site BFF/reverse proxy or an OAuth2/OIDC architecture rather than opening CORS to all origins to "fix" cookies.

## 16. Should Stateless APIs Use This Approach?

**No**, if the real requirement is a token-based stateless API. In a stateless flow:
- every request carries a verified bearer token or API key;
- `SecurityContextRepository` can be `NullSecurityContextRepository`;
- nothing relies on HttpSession;
- `SessionCreationPolicy.STATELESS` is appropriate;
- clients handle token expiration/revocation/refresh flows accordingly.

In this exercise's **session-based JSON login**:
- the password is sent only at login;
- the backend issues an HttpSession (`JSESSIONID`);
- the browser sends the cookie automatically after login;
- context is saved in the session repository;
- CSRF must be evaluated and remains enabled in the example;
- logout invalidates the session.

**Storing a JWT inside an automatically sent cookie** does not eliminate CSRF risk; cookies remain ambient credentials. Never decide whether to enable CSRF merely because an endpoint path starts with `/api/`.

## 17. Multiple SecurityFilterChains: Ensuring Requests Hit the Right Repository

A hybrid system might define:

```text
@Order(1): /api/token/**
  Stateless bearer JWT
  NullSecurityContextRepository
  CSRF policy based on bearer headers and threat model

@Order(2): /api/auth/**, /web/**
  Stateful JSON login + session cookie
  HttpSessionSecurityContextRepository
  Session CsrfTokenRepository
```

Spring Security selects **the first matching chain**, rather than running every chain. If a catch-all stateless chain precedes the stateful login chain, requests hit the wrong repository, causing login to return 200 while `/me` stays anonymous. Test matchers, precedence, request cache, CSRF, and session policies for **every chain**.

Never put `csrf.disable()` on the session chain just because another bearer endpoint doesn't need CSRF. Never fall back to cookie-based login for bearer APIs without analyzing ambient credentials.

## 18. Concurrency and Saving Context

A single `HttpSession` can serve multiple concurrent requests. `SecurityContextHolder` is per-thread for the **currently executing request**, while the session repository stores shared state. If logout occurs while another request is mid-flight, the older request may already hold an `Authentication` snapshot prior to session invalidation.

For highly sensitive operations, re-validate authorization/token revocation close to the commit point per threat model; never assume a logout response retroactively aborts all in-flight operations.

Key principles:

- Never store `SecurityContext` in a static field to "share" across requests.
- Never copy ThreadLocals into async executors via shared global variables.
- For asynchronous code, use Spring Security context propagation or pass verified identity explicitly and re-check permissions where needed.
- Mitigate simultaneous login/submission races, session fixation, session timeouts, and session reuse.
- In clusters, use Spring Session/Redis or a shared session solution suited to your architecture; never assume pod A's in-memory HttpSession exists on pod B.
- Ensure session serialization compatibility when storing in Redis, especially when changing principal classes across releases.

### 18.1. Authentication Events and Auditing

A custom controller calls `AuthenticationManager` directly, so audit events emitted by the manager/publisher and interactive events from framework filters may differ from default form login. If you construct a `ProviderManager` manually and need `AuthenticationSuccessEvent`/failure events, wire an `AuthenticationEventPublisher` explicitly rather than assuming a custom manager publishes them by default. Avoid logging raw passwords or full `Authentication` objects.

When audits serve compliance, store them durably with proper dedup/replay handling; in-process Spring application events do not guarantee exactly-once durability.

## 19. Symptom-Based Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| POST JSON login returns 403 | Missing/invalid CSRF token | GET /csrf, same cookie jar, CSRF header |
| POST login returns 415 | Content-Type is not application/json | Send `Content-Type: application/json` |
| POST login returns 400 | Malformed JSON or blank username/password | Inspect body binding and validation |
| POST login returns 401 | Invalid credentials or auth exception | Inspect manager/provider server-side, never log passwords |
| POST login returns 200 yet GET /me is 401 | Forgot `saveContext`, session/repo mismatch, cookie not sent | Inspect session, repository, `Set-Cookie`, and next `Cookie` |
| Valid login does not rotate session ID | Strategy not called or no prior session existed | GET /csrf creates session before login; verify `changeSessionId` |
| POST after login returns 403 | Reusing pre-login CSRF token that was cleared/rotated | Fetch a fresh `GET /csrf` after login |
| POST logout returns 403 | Missing fresh token or wrong session | `GET /csrf` in current session and send header |
| JSON logout returns 200 yet /me still returns 200 | Session/repository was not invalidated | Use `LogoutFilter`; inspect session store/cache |
| GET /me returns 302 HTML | `formLogin` entry point still enabled | Configure 401 API entry point and matching chain |
| Logged-in user gets 403 on /api/admin | USER role is not ADMIN | Check authorization rules, not password verification |
| Browser lacks cookie despite backend 200 | SameSite/Secure/Domain/Path/proxy/third-party policies | Inspect `Set-Cookie` and browser DevTools |
| Postman/curl works yet browser hits CORS error | CORS only applies to browsers; wrong preflight/credentials | Inspect OPTIONS, Origin, and response headers |
| Session lost between two pods | Unshared local session store | Session replication / Spring Session / sticky sessions |
| Multi-node ClassCast/serialization errors | Incompatible custom principal/session format across releases | Versioning / rolling deployment compatibility |
| AccessDeniedException turns into 500 | Custom filter before exception translation or wrong controller boundary | Filter order and handler responsibilities |
| Old session keeps privileges after role change | Stale persisted authorities | Session revocation / reauth / permission refresh |
| Duplicate login actions | Frontend retries, double clicks, gateway retries | Request IDs, anti-brute-force, idempotency policies |

### 19.1. 8-Step Debugging Procedure

1. Confirm which **`SecurityFilterChain`** matches `/api/auth/login` and `/api/auth/me`.
2. Verify POST carries the CSRF header and the **same `JSESSIONID` cookie** from `GET /csrf`.
3. Check whether `manager.authenticate(...)` returns an `Authentication` or throws, without printing passwords.
4. Confirm `sessionStrategy.onAuthentication(...)` runs after success.
5. Verify the controller calls `SecurityContextHolder.setContext(...)` and `repository.saveContext(...)` **before response commit**.
6. Verify the client receives the rotated session cookie and sends it on `GET /me`.
7. Check that `GET /me` loads `Authentication` from the **same repository**, the session hasn't expired, and authorities match.
8. For logout, verify a fresh CSRF token, session invalidation, and `GET /me` returning 401.

In isolated dev environments you may raise Spring Security DEBUG logs, but never enable wire logging capturing `Authorization`, `Cookie`, raw passwords, or CSRF tokens in production.

## 20. Production Extensions: What the Demo Deliberately Omits

| Item | Demo | Production Requirement |
| --- | --- | --- |
| User store | `InMemoryUserDetailsManager` | Database/directory/IdP with safe migrations |
| Password | Lab env variable, BCrypt | Password policy, reset, breach checks, encoder upgrades |
| Credential errors | Generic 401 | Separate monitoring for bad credentials vs. outages |
| Anti-brute-force | Omitted | Rate limiting, adaptive controls, suitable lockouts |
| Session | Local HttpSession | Secure cookies, rotation, multi-node store, expiry |
| CSRF | Session token | SPA integration/BREACH handling, token lifecycle tests |
| MFA/passkey | Omitted | Risk-based step-up and assurance |
| Auth events | Minimal | Event publisher, auditing, safe logging, incident response |
| Logout | Spring LogoutFilter | Revoke remember-me/sessions/devices per policy |
| Disabled/locked accounts | In-memory enabled demo | Account state checks, admin actions, recovery |
| CORS | Same-origin | Explicit allowlist if cross-origin |
| TLS | Localhost HTTP lab | HTTPS, proxy trust, HSTS, secure cookies |
| Session concurrency | Unbounded | `SessionRegistry` / distributed strategy |
| Error schema | Minimal JSON/HTTP status | API versioning, content negotiation, Problem Details |
| Tests | MockMvc | Embedded server/browser/E2E, proxy, concurrency, chaos |

**Never copy sample passwords, session cookie settings, or dev CORS configs into real environments.** Security settings must derive from policy and operational requirements.

## 21. Self-Check Questions

1. **Why can a controller call `authenticate`, return 200, and still lose login on the next request?** Because `saveContext` was never called on the repository.
2. **Which `Authentication` object gets saved?** The object **authenticated by the manager**, not the client-supplied candidate holding the raw password.
3. **In Spring Security 6, what does `SecurityContextHolderFilter` do?** Primarily reads/restores the context; custom code wanting persistence must save explicitly.
4. **When should `SessionAuthenticationStrategy` be called?** After the manager authenticates successfully, before saving context/returning the response.
5. **What does `ChangeSessionIdAuthenticationStrategy` defend against?** Session fixation; it does not replace password verification.
6. **Why can `GET /csrf` create a session even before login?** The CSRF repo needs to persist the expected token; having a session does not mean authenticated.
7. **Why is a fresh CSRF token needed after login?** `CsrfAuthenticationStrategy` clears the previous token.
8. **Why do two different CSRF token strings not automatically prove the persisted token rotated?** Because `XorCsrfTokenRequestAttributeHandler` produces a fresh masked value per request.
9. **Is a 403 on POST login without CSRF a password error?** No; the request is blocked before reaching the controller.
10. **If POST login with wrong password returns 401 and GET /me returns 401, what does that prove?** No valid `Authentication` was persisted.
11. **If POST login returns 200 and GET /me returns 200 with the same cookie, what is proven?** Session persistence of `SecurityContext` works end-to-end at the flow level.
12. **Why not use `SessionCreationPolicy.STATELESS` here?** It conflicts with persisting authentication inside HttpSession.
13. **Why disable `formLogin` in the demo?** To prevent HTML/form processing filters from interfering with the JSON contract.
14. **Why should logout use `LogoutFilter`?** It properly coordinates session/context/CSRF/remember-me cleanup.
15. **Does storing a JWT in a cookie eliminate the need for CSRF?** No; cookies are still attached automatically by browsers.
16. **What does a cross-origin frontend need beyond sessions?** CORS allowlist, credentialed fetch, proper SameSite/Secure/Domain cookies, and CSRF.
17. **If a user has `USER` but not `ADMIN`, what should `/api/admin` return?** 403, not 401 bad password.
18. **Should a cookie's Session ID be used directly as a user ID?** No; sessions are opaque and must be looked up/validated server-side.
19. **If an app runs two pods without shared sessions, what happens?** Requests routed to the other pod can appear anonymous despite a prior successful login.
20. **Are MockMvc tests enough to guarantee production cookie safety?** No; browser/TLS/reverse-proxy testing is still required.

## 22. Acceptance Checklist and Official Documentation

### Checklist

- [ ] `POST /api/auth/login` accepts JSON and verifies credentials via the provider.
- [ ] Failed login creates no authenticated context and returns a generic public 401.
- [ ] Valid login creates a new `SecurityContext`, sets the holder, and calls **`saveContext`** on the same repository used by the filter chain.
- [ ] Session strategy mitigates session fixation; session ID changes when a pre-login session exists.
- [ ] CSRF is enforced on POST login and logout; pre-login tokens are invalidated upon login.
- [ ] `GET /csrf` sets `Cache-Control: no-store`, and tokens are never treated as login proof.
- [ ] A second request carrying only the cookie restores the principal from the repository.
- [ ] Anonymous `/api/auth/me` receives 401; authenticated user receives 200.
- [ ] Protected actions lacking roles receive 403.
- [ ] Standard logout invalidates the session and clears context/CSRF, rather than merely clearing variables in a controller.
- [ ] JSON responses never expose passwords, raw exceptions, tokens, or session IDs.
- [ ] No static `Authentication` or stateless chain is used to fake session persistence.
- [ ] Session cookies/TLS/proxy/CORS/SameSite are browser-tested in the target deployment environment.
- [ ] Rate limiting, auditing, MFA/step-up, and session revocation follow product policy.
- [ ] Tests were executed against the actual target Spring Boot/Security versions prior to deployment.

### Reference Documentation

- Spring Security 6.5 – Authentication Persistence and Session Management (manual save): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 – Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 – CSRF, deferred token and SPA handling: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 – Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 – SecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security 6.5 – HttpSessionSecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html
- Spring Security 6.5 – CsrfAuthenticationStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html
- Spring Security 6.5 – ChangeSessionIdAuthenticationStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html
- Spring Security 6.5 – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Boot 3.5 – Servlet Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
