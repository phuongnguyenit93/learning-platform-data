# Authenticating via AuthenticationManager Instead of Comparing Passwords in the Controller

> **Scope:** JSON login in **Spring Security Servlet 6.x**, illustrated with Spring Boot 3.3.5 and Java 17+. The main topic is building an endpoint that accepts `username/password` via JSON, calls `AuthenticationManager.authenticate(...)`, and handles success/failure properly; the session and CSRF sections explain the conditions for login to actually persist across multiple HTTP requests.

## 1. Why Not Check Passwords Directly in the Controller?

A client sends:

```http
POST /api/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"secret123"}
```

**Bad anti-pattern**, illustrating logic to avoid, not standalone Java code:

```java
UserRecord user = userRepository.findByUsername(body.username());
if (user != null && user.password().equals(body.password())) {
    return "login success";
}
return "login failed";
```

This snippet both easily leads to storing plaintext passwords and bypasses the protective layers Spring Security provides. Passwords must be stored as an appropriate hash (e.g., salted BCrypt), never compared with `equals` against a raw password. Even if you call `passwordEncoder.matches(raw, hash)` yourself in the Controller, you can still miss disabled/locked/expired account checks, multi-`AuthenticationProvider` logic, authentication events, and standardized error handling. Returning the string `"login success"` also **does not create** an authenticated `Authentication` in `SecurityContext`.

The goal is clear separation of responsibilities:

| Component | Primary role |
| --- | --- |
| `@RestController` | Receives JSON, validates required inputs, builds the request token, calls the manager, and picks the HTTP response |
| `UsernamePasswordAuthenticationToken.unauthenticated(...)` | Wraps username/password as an **unauthenticated** `Authentication` |
| `AuthenticationManager` | Credential authentication API; returns a successful `Authentication` or throws `AuthenticationException` |
| `ProviderManager` | Commonly used manager implementation, delegating in turn to providers supporting the token |
| `DaoAuthenticationProvider` | Loads `UserDetails`, verifies the password via `PasswordEncoder.matches(...)`, and checks account flags |
| `SecurityContextHolder` | Holds the current context and identity during the request |
| `SecurityContextRepository` | Saves/restores identity across requests when using sessions |
| `SessionAuthenticationStrategy` | Applies post-login session protections, such as rotating session ID and refreshing the CSRF token |
| `AuthorizationFilter` | Checks access permissions based on `Authentication` and authorities |

Never let the client send arbitrary authorities/roles in JSON and trust them as real permissions. Roles must be loaded by the server from a verified data source.

## 2. How Is AuthenticationManager Actually Invoked?

```text
Client POST /api/login + JSON (+ cookie and CSRF token when using session)
  |
  v
Servlet SecurityFilterChain
  |-- CsrfFilter protects POST
  |-- AuthorizationFilter for /api/login: permitAll
  v
AuthController.login(LoginRequest)
  |
  |-- UsernamePasswordAuthenticationToken.unauthenticated(username, password)
  |-- AuthenticationManager.authenticate(requestToken)
  |     |
  |     v
  |     ProviderManager
  |        -> DaoAuthenticationProvider
  |              -> UserDetailsService.loadUserByUsername(username)
  |              -> PasswordEncoder.matches(rawPassword, storedHash)
  |              -> check account flags and collect authorities
  |        <- Authenticated Authentication
  |
  |-- failure: AuthenticationException -> generic HTTP 401 response
  |
  |-- success:
        SessionAuthenticationStrategy.onAuthentication(...)
        SecurityContext context = SecurityContextHolder.createEmptyContext()
        context.setAuthentication(authenticated)
        SecurityContextHolder.setContext(context)
        SecurityContextRepository.saveContext(context, request, response)
        -> HTTP 200 JSON response (without password)
  |
  v
Client stores the new session cookie
  | GET /api/me + cookie
  v
SecurityContextRepository restores context from session
  -> AuthorizationFilter permits /api/me
  -> Controller returns identity info
```

### 2.1. The Token Passed to the Manager Is Unauthenticated

In the Controller:

```java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginRequest.username(), loginRequest.password());

Authentication authenticated = authenticationManager.authenticate(requestToken);
```

This is a snippet inside a method, not a standalone runnable `main`. `requestToken.isAuthenticated()` is initially `false`. Upon success, the manager typically returns a token with `isAuthenticated() == true`, a verified `principal`, and `GrantedAuthority` instances. **Never call** `UsernamePasswordAuthenticationToken.authenticated(...)` yourself for client-supplied data.

`AuthenticationManager.authenticate(Authentication)` **does not return a boolean**. It returns a successful `Authentication` or throws an exception such as `BadCredentialsException`, `DisabledException`, or `LockedException`. Do not return raw exception messages to the client; a generic 401 response reduces username enumeration risk.

### 2.2. Provider, UserDetailsService, and PasswordEncoder

For username/password, `ProviderManager` finds a provider supporting `UsernamePasswordAuthenticationToken`. `DaoAuthenticationProvider` loads `UserDetails` from `UserDetailsService`, then `PasswordEncoder.matches(rawPassword, storedHash)` verifies the password. The provider also checks enabled, non-locked, non-expired, and credentials-non-expired flags per Spring Security's mechanism.

With BCrypt, for example, `encode("secret123")` can produce a different hash on every call because of salting. Never use `encode(raw).equals(storedHash)`; use `matches(raw, storedHash)`. When switching to a database, LDAP, or another provider, the Controller still works with the `AuthenticationManager` interface without needing to know how hashes are stored.

### 2.3. Manager Authentication Alone Does Not Log In a Session Automatically

If a controller calls the manager directly, **the controller itself must set and save the context**. In Spring Security 6, `SecurityContextHolderFilter` primarily loads the context; it does not automatically write every controller change to the session. You need:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, servletRequest, servletResponse);
```

`SecurityContextHolder.setContext` takes effect for the current request; `saveContext` uses the repository to persist the context for later requests. The filter chain and controller must share the same `SecurityContextRepository`.

When building a custom JSON login, you must also consider what standard authentication filters normally do: rotating the session ID against **session fixation**, refreshing the CSRF token, and handling logout. The runnable example below demonstrates an explicit session strategy.

## 3. Complete Example: JSON Login + Session + CSRF

Stack: Spring Boot **3.3.5**, Java **17+**, Maven **3.9+**, Spring Security 6.x. The demo has user `alice` / password `secret123` / authority `ROLE_READER`. The password is for example purposes only and is BCrypt-hashed at application startup. Real apps must use HTTPS and secure user/secret stores.

Endpoints:

| Endpoint | Role | Success result |
| --- | --- | --- |
| `GET /api/csrf` | Fetch CSRF token for the client to send on POSTs | 200 JSON |
| `POST /api/login` | JSON username/password -> manager -> save session | 200 JSON |
| `GET /api/me` | Read identity from the saved SecurityContext | 200 JSON |
| `POST /api/logout` | Logout handled by Spring Security `LogoutFilter` | 204 |

Directory layout:

```text
json-login-demo/
├── pom.xml
├── src/main/java/com/example/jsonlogin/JsonLoginApplication.java
└── src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java
```

### 3.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>json-login-demo</artifactId>
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

### 3.2. src/main/java/com/example/jsonlogin/JsonLoginApplication.java

```java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
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

import java.util.List;

@SpringBootApplication
public class JsonLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("secret123"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository contextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contextRepo,
            CsrfTokenRepository csrfTokens) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .securityContext(sc -> sc.securityContextRepository(contextRepo))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, auth) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
            );

        return http.build();
    }

    public record LoginRequest(String username, String password) {}
    public record LoginResponse(String username, List<String> authorities) {}
    public record ErrorResponse(String message) {}

    @RestController
    public static class AuthController {
        private final AuthenticationManager authenticationManager;
        private final SecurityContextRepository contextRepository;
        private final SessionAuthenticationStrategy sessionStrategy;

        public AuthController(
                AuthenticationManager authenticationManager,
                SecurityContextRepository contextRepository,
                SessionAuthenticationStrategy sessionStrategy) {
            this.authenticationManager = authenticationManager;
            this.contextRepository = contextRepository;
            this.sessionStrategy = sessionStrategy;
        }

        @GetMapping("/api/csrf")
        public CsrfToken csrf(CsrfToken token) {
            return token;
        }

        @PostMapping("/api/login")
        public ResponseEntity<?> login(
                @RequestBody LoginRequest body,
                HttpServletRequest request,
                HttpServletResponse response) {

            if (body == null || body.username() == null || body.password() == null
                    || body.username().isBlank() || body.password().isBlank()) {
                return ResponseEntity.badRequest()
                        .body(new ErrorResponse("username/password required"));
            }

            try {
                Authentication requestToken =
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                body.username(), body.password());

                // Password verification is handled by the provider, not the Controller.
                Authentication authenticated =
                        authenticationManager.authenticate(requestToken);

                sessionStrategy.onAuthentication(authenticated, request, response);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authenticated);
                SecurityContextHolder.setContext(context);

                contextRepository.saveContext(context, request, response);
                return ResponseEntity.ok(toResponse(authenticated));

            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                        .body(new ErrorResponse("Invalid login credentials"));
            }
        }

        @GetMapping("/api/me")
        public LoginResponse me(Authentication auth) {
            return toResponse(auth);
        }

        private static LoginResponse toResponse(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            return new LoginResponse(auth.getName(), authorities);
        }
    }
}
```

### 3.3. Explaining Key Decisions

1. `AuthenticationManager` is explicitly configured via `ProviderManager`/`DaoAuthenticationProvider` to make clear where credentials are checked. The Controller only knows the manager interface and never retrieves users/password hashes.
2. The `SecurityContextRepository` bean is the **exact same instance** in the Controller and `SecurityFilterChain`. If the two sides save/load from different places, subsequent requests can lose identity.
3. `SessionAuthenticationStrategy` is called after success, before saving the context. `ChangeSessionIdAuthenticationStrategy` rotates the session ID; `CsrfAuthenticationStrategy` clears the old token. The client must call `GET /api/csrf` again after login.
4. `permitAll()` on `/api/login` only waives requiring prior login; it **does not disable** `CsrfFilter`. A POST missing a valid CSRF token returns 403 even if the password is right.
5. `httpBasic` and `formLogin` are disabled so the demo has only the JSON flow. `@PostMapping("/api/login")` does not automatically become one of Spring Security's built-in authentication filters.
6. `exceptionHandling` sets an entry point returning 401 for protected GET endpoints when no session exists. Authenticated users lacking roles on another endpoint typically receive 403.
7. `LogoutFilter` handles `POST /api/logout`, invalidating the session by default and returning 204. No custom controller is needed to clear the session.
8. The success response contains only the username and roles from the manager, with no password or password hash.

## 4. Running and Testing via HTTP

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

### 4.1. Bash/macOS/Linux: cookie jar + CSRF

Example using `curl` and `python3`, with the same `cookies.txt` file holding the `JSESSIONID` cookie. The token is extracted from JSON, so there is no hardcoded value.

```bash
# 1. Obtain CSRF token + session cookie before POSTing.
csrf_token=$(curl -sS -c cookies.txt http://localhost:8080/api/csrf \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 2. Log in with JSON, sending the cookie and CSRF from the same session.
curl -i -sS -b cookies.txt -c cookies.txt \
    -H "X-CSRF-TOKEN: $csrf_token" \
    -H 'Content-Type: application/json' \
    --data '{"username":"alice","password":"secret123"}' \
    http://localhost:8080/api/login

# 3. Subsequent request does not send password: only keeps the updated cookie.
curl -i -sS -b cookies.txt http://localhost:8080/api/me

# 4. Login rotated the CSRF token; fetch a new token before the next POST.
new_token=$(curl -sS -b cookies.txt -c cookies.txt http://localhost:8080/api/csrf \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 5. Logout via LogoutFilter.
curl -i -sS -b cookies.txt -c cookies.txt \
    -H "X-CSRF-TOKEN: $new_token" \
    -X POST http://localhost:8080/api/logout

# 6. After logout, the old cookie no longer represents a logged-in user.
curl -i -sS -b cookies.txt http://localhost:8080/api/me
```

Typical results:

| Request | HTTP status | Notes |
| --- | --- | --- |
| GET `/api/csrf` | 200 | JSON with `headerName`, `parameterName`, `token` |
| POST `/api/login` valid password/CSRF | 200 | Body `{"username":"alice","authorities":["ROLE_READER"]}` |
| GET `/api/me` with post-login session | 200 | Returns Alice's username/authorities |
| POST `/api/logout` with new CSRF token | 204 | Empty body |
| GET `/api/me` after logout | 401 | Error body may depend on Spring Boot |
| POST login missing or wrong CSRF | 403 | `CsrfFilter` rejects before Controller |
| POST login with CSRF but wrong password | 401 | `AuthenticationManager`/provider rejects |
| POST login with CSRF but blank username/password | 400 | Simple controller validation |

Running locally over HTTP is for learning. Transmitting credentials and cookies over a real network requires **HTTPS/TLS**.

### 4.2. Windows PowerShell

Without Bash or an external JSON parser, use `WebRequestSession` to hold cookies:

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$csrf = Invoke-RestMethod -Method Get -Uri 'http://localhost:8080/api/csrf' -WebSession $session
$login = Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/login' -WebSession $session -Headers @{ 'X-CSRF-TOKEN' = $csrf.token } -ContentType 'application/json' -Body '{"username":"alice","password":"secret123"}'
$login
Invoke-RestMethod -Method Get -Uri 'http://localhost:8080/api/me' -WebSession $session
```

`Invoke-RestMethod` returns an object with `username = alice` and `authorities = ["ROLE_READER"]`. If you want to make another POST after login, fetch a new CSRF token first.

## 5. Testing with MockMvc

Create `src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java`:

```java
package com.example.jsonlogin;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginApplicationTests {
    private static final String GOOD_LOGIN = """
            {"username":"alice","password":"secret123"}
            """;

    @Autowired
    MockMvc mvc;

    @Test
    void jsonLoginPersistsAuthenticationBetweenRequests() throws Exception {
        // Create a CSRF token and session via an unauthenticated GET.
        MvcResult initial = mvc.perform(get("/api/csrf"))
                .andExpect(status().isOk())
                .andReturn();
        MockHttpSession session =
                (MockHttpSession) initial.getRequest().getSession(false);
        assertNotNull(session);
        String token = JsonPath.read(
                initial.getResponse().getContentAsString(), "$.token");

        MvcResult login = mvc.perform(post("/api/login")
                    .session(session)
                    .header("X-CSRF-TOKEN", token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(GOOD_LOGIN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_READER"))
                .andReturn();

        MockHttpSession authenticatedSession =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(authenticatedSession);

        // Next request loads Authentication via repository from the session.
        mvc.perform(get("/api/me").session(authenticatedSession))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void csrfFailureAndBadCredentialsAreDifferent() throws Exception {
        mvc.perform(post("/api/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(GOOD_LOGIN))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/login")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"alice","password":"wrong"}
                            """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message")
                        .value("Invalid login credentials"));

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Run tests:

```bash
mvn test
```

The first test uses the **actual CSRF token returned by the endpoint** to log in, then reuses the updated session in another HTTP request. This verifies that the manager's authentication result was persisted and the next request does not need to resend the password. The second test distinguishes CSRF 403 from bad-credential 401 and unauthenticated 401.

`MockMvc` executes the Servlet filter chain and controller in a test environment without opening a server port. `with(csrf())` is a `spring-security-test` utility, not a production setting that disables CSRF.

## 6. Security and Design Notes

### 6.1. Distinguishing Authentication, Authorization, and Persistence

- **Authentication:** `AuthenticationManager` verifies identity/credentials and returns an `Authentication`.
- **Authorization:** rules like `hasRole("ADMIN")` use authorities in `Authentication` to allow/deny access.
- **Persistence:** `SecurityContextRepository` retains identity across requests when using sessions. The manager does not handle this itself.
- **JWT:** If switching to Bearer tokens, you must issue signed tokens with appropriate lifetimes/claims and verify tokens on every request. Simply calling `authenticate` does not generate a JWT.

| Application style | After authenticate | Next request |
| --- | --- | --- |
| Session/cookie (demo) | `SecurityContextRepository.saveContext` into session, rotate session ID | Client sends cookie; server loads context |
| Stateless token | Issue a secure credential/token via an appropriate component | Client sends Bearer token; filter verifies signature/expiry |

Never configure `SessionCreationPolicy.STATELESS` and expect `HttpSessionSecurityContextRepository` to keep a logged-in session.

### 6.2. CSRF Remains Important with JSON Using Cookies

CSRF depends on **credentials automatically sent by the browser** such as cookies, not on whether the body is JSON or a form. `permitAll` does not disable `CsrfFilter`. The demo keeps `HttpSessionCsrfTokenRepository`; the client fetches the token via `GET /api/csrf` and sends it in the `X-CSRF-TOKEN` header on POSTs. On successful login, `CsrfAuthenticationStrategy` clears the old token; the client fetches a new one. Never arbitrarily call `csrf.disable()` for an API called by browsers with session cookies.

If the frontend is on a different origin, configure CORS, `Secure`/`HttpOnly`/`SameSite` cookies, and credential-sending policies consistently. Production login must use HTTPS; never log raw passwords, session IDs, or CSRF tokens.

### 6.3. Session Fixation and Logout

A custom Controller calling the manager **does not automatically trigger** the full lifecycle of a standard authentication filter. The demo explicitly calls `SessionAuthenticationStrategy` after `authenticate` to rotate the session ID, reducing session fixation risk, and refresh the CSRF token. `LogoutFilter` uses Spring Security's `SecurityContextLogoutHandler` to tear down the session; never replace it with merely clearing frontend state.

### 6.4. Common Mistakes

1. Comparing passwords yourself in the Controller using `equals` or `PasswordEncoder.matches`.
2. Using `UsernamePasswordAuthenticationToken.authenticated(...)` with unverified credentials.
3. Assuming `AuthenticationManager.authenticate(...)` returns a boolean.
4. Returning 200 JSON while forgetting `SecurityContextRepository.saveContext`.
5. Using different repositories between the Controller and `SecurityFilterChain`.
6. Not calling the session authentication strategy when building a custom login flow.
7. Forgetting to refresh the CSRF token after login when `CsrfAuthenticationStrategy` is active.
8. Disabling CSRF solely because the API accepts JSON and uses cookies.
9. Returning `AuthenticationException.getMessage()` to the client, leaking account state.
10. Letting the client declare roles/authorities in `LoginRequest`.
11. Thinking a successful JSON login automatically issues a JWT.
12. Skipping rate limiting, brute-force protection, MFA when needed, and security event logging.
13. Not using HTTPS, or logging passwords/hashes/cookies.
14. Treating 401 (missing/wrong credentials) as identical to 403 (authenticated but lacking permissions or CSRF rejected).

## 7. Self-Assessment Questions

1. Why is `AuthenticationManager` better than writing `if (password.equals(...))` in the Controller?
2. Who actually calls `PasswordEncoder.matches` when using `DaoAuthenticationProvider`?
3. How does `UsernamePasswordAuthenticationToken.unauthenticated` differ from the returned `Authentication`?
4. Why does calling only `SecurityContextHolder.setContext` while forgetting `saveContext` cause the next request to still return 401?
5. Why can a POST `/api/login` with the right password still get a 403 from `CsrfFilter`?
6. Why must the session ID and CSRF token be handled when a custom Controller authenticates directly?
7. If you later switch from sessions to JWTs, which steps must change alongside `AuthenticationManager`?

**Key answers:** (1) the manager enforces provider/account policies consistently; (2) the provider; (3) the input is unauthenticated, the result is verified; (4) the context only exists for the current request; (5) CSRF is a protection layer before the Controller; (6) reduces session fixation and protects cookie-based requests; (7) issuing and verifying signed/expiring tokens instead of session persistence.

## 8. Official Documentation

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — Session Management / Storing Authentication Manually: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF, token endpoint and JavaScript clients: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — AuthenticationManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html
