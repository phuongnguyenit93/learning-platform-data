# Saving SecurityContext and Applying Session Strategies in JSON Login with Spring Security Servlet

## Learning Objectives

Many Spring MVC applications use form `POST /login` with `UsernamePasswordAuthenticationFilter`. When writing a custom **POST /api/login endpoint accepting JSON**, developers often call `AuthenticationManager.authenticate(...)` and return HTTP 200. That is **not enough** to maintain a login session across subsequent requests.

A login based on an **HTTP session cookie** requires at least three separate responsibilities:

1. Authenticating username/password: `AuthenticationManager` returns an authenticated `Authentication`.
2. Handling session strategies: `SessionAuthenticationStrategy` enforces policies required at login time, such as rotating the session ID against session fixation, refreshing the CSRF token, or enforcing concurrent session limits if configured.
3. Saving the SecurityContext: `SecurityContextRepository.saveContext(...)` allows the `Authentication` to be reloaded on future requests. Placing `Authentication` into `SecurityContextHolder` only resolves the context for the current request/thread.

This lesson explains how to separate those responsibilities, pick the right APIs, and implement a cookie-session JSON login flow in **Spring Security Servlet 6.x / Spring Boot 3.x / Java 17+**.

After studying, you will be able to:

- Explain how `SecurityContextHolder`, `SecurityContext`, `Authentication`, and `SecurityContextRepository` collaborate.
- Understand why Spring Security 6 emphasizes **explicit save** when using `SecurityContextHolderFilter`.
- Use a custom `AbstractAuthenticationProcessingFilter` to accept JSON and leverage the standard authentication lifecycle.
- Configure the same `SecurityContextRepository` for the login filter and protected requests.
- Wire `CompositeSessionAuthenticationStrategy` with `ChangeSessionIdAuthenticationStrategy` and `CsrfAuthenticationStrategy`.
- Understand the impact of `SessionCreationPolicy.IF_REQUIRED` compared to `STATELESS`.
- Enable CSRF for browsers using session cookies and expose `GET /csrf` to retrieve tokens.
- Write a runnable application tested with `MockMvc` for login success/failure, follow-up requests, CSRF, and logout.
- Diagnose "login returns 200 yet next request still gets 401", session fixation, session cookies, CSRF, and multiple `SecurityFilterChain`s.

**Scope:** Servlet applications with **JSON login that persist state in HttpSession**. If using Bearer tokens/JWTs in a stateless design, the approach differs and you should not force writing SecurityContext into a session.

## 1. Authentication Does Not Automatically Mean a Persistent Login Session

Suppose a browser sends:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: <valid-token>

{"username":"learner","password":"local-pass-123"}
~~~

The CSRF value is only an illustrative symbol. For session-based browsers, you must send the real token issued by the server alongside the associated cookie.

Hand-written code often looks like:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));
SecurityContextHolder.getContext().setAuthentication(verified);
return ResponseEntity.ok().build();
~~~

This is an **incomplete illustrative snippet**, not a recommended implementation. It may let handlers see `Authentication` on the current thread, yet when the request finishes, the security context is cleared from the thread. Subsequent requests load context via a security filter from `SecurityContextRepository`; without an appropriate save operation, the app **does not know** the previous login succeeded.

Login data should not live permanently in an app-managed static variable or ThreadLocal. Spring Security provides a `SecurityContext` lifecycle, repository mechanism, and filters handling consecutive requests.

### Distinguishing the Objects

| Object | Responsibility |
| --- | --- |
| AuthenticationManager | Verifies an authentication request and returns a valid Authentication or throws AuthenticationException |
| Authentication | Principal and authorities; an authenticated object typically has `isAuthenticated() = true` |
| SecurityContext | Container holding the Authentication for a security context |
| SecurityContextHolder | API accessing context for the current thread/strategy, not a session persistence database |
| SecurityContextRepository | Loads/saves context across requests, e.g., via HTTP session |
| SecurityContextHolderFilter | Loads context from repository for the request and clears the holder; does not auto-save for custom code |
| SessionAuthenticationStrategy | Applies policies upon authentication success: session fixation, CSRF, concurrency... |
| SecurityFilterChain / FilterChainProxy | Selects the filter set matching each HTTP request |
| HttpSession | A server-side state store identified by a session ID via a cookie such as JSESSIONID |

**SecurityContextRepository and SessionAuthenticationStrategy do not replace each other.** A repository can save context without running session fixation policies. A session strategy can rotate session IDs without saving Authentication for future requests.

## 2. Full Flow for JSON Login + Cookie-Session

~~~text
(1) Browser fetches CSRF token:
    GET /csrf
        |
    CsrfFilter + HttpSessionCsrfTokenRepository
        |
    JSON containing token, initial session cookie if needed

(2) Browser sends credentials:
    POST /api/login
    Cookie: JSESSIONID=...
    X-CSRF-TOKEN: ...
    Content-Type: application/json
        |
    FilterChainProxy selects SecurityFilterChain
        |
    CsrfFilter verifies token
        |
    JSON login filter matches exact POST /api/login
        |
    AuthenticationManager.authenticate(...)
        |
        +-- error -> unsuccessfulAuthentication -> 401 JSON
        |
        +-- success -> SessionAuthenticationStrategy.onAuthentication(...)
                         |
                   rotate session ID if a session exists
                   refresh/invalidate CSRF token per policy
                         |
                   create SecurityContext with Authentication
                         |
                   SecurityContextHolder.setContext(context)
                         |
                   SecurityContextRepository.saveContext(context,...)
                         |
                   success handler -> 200 JSON

(3) Subsequent request:
    GET /api/me + new/valid session cookie
        |
    SecurityContextHolderFilter loads context from repository
        |
    AuthorizationFilter requires authenticated()
        |
    Controller sees active Authentication
        |
    response 200; filter clears holder after request
~~~

The flow above diagrams **responsibilities**, without guaranteeing every filter in Spring Security 6 calls steps in the exact same order across all mechanisms. This lesson's example is built on `AbstractAuthenticationProcessingFilter`: the framework invokes the session strategy after successful authentication and handles context saving in `successfulAuthentication(...)`, before the success handler completes the response.

### What If Login Fails?

There is no successful `Authentication` to save, and the success-branch session strategies do not run. The failure handler returns a generic message; never expose passwords, exact failure reasons, or sensitive data in the response. A wrong password must never leave an authenticated `SecurityContext`.

### What If the CSRF Token Is Missing?

The CSRF filter can return 403 **before** the custom JSON login filter receives the request. This is not a `BadCredentialsException` and does not mean `AuthenticationManager` checked the password. Use `GET /csrf` and a valid header instead of disabling CSRF arbitrarily.

## 3. Step One: Create an Authentication Verified by the Manager

The common path is `UsernamePasswordAuthenticationToken.unauthenticated(...)`:

~~~java
UsernamePasswordAuthenticationToken requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

Authentication verified =
        authenticationManager.authenticate(requestToken);
~~~

This is an **excerpt**, not a complete controller/filter. Crucially, do not do this:

~~~java
// Wrong idea: self-marking authenticated without going through AuthenticationManager.
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                "learner", null, java.util.List.of());
~~~

The misguided code above can create a token marked authenticated without verifying credentials; never use it to grant a session to untrusted requests.

`AuthenticationManager` (typically `ProviderManager` + `AuthenticationProvider`) verifies passwords via `PasswordEncoder`/`UserDetailsService` or an appropriate mechanism. On success, the returned object holds the verified principal and authorities.

Only after obtaining a verified `Authentication` should you apply the session strategy, set `SecurityContext`, and save it. With framework-supported filters, prefer letting the framework run this sequence; avoid reimplementing it unnecessarily.

## 4. Step Two: SecurityContextRepository Is Where Login Persists

### SecurityContextHolder Lives Only for the Request/Thread

`SecurityContextHolder` typically uses `ThreadLocal`. In Servlet apps, `SecurityContextHolderFilter` sets up context for the request and clears it at the end to prevent leaking context across pooled threads.

Therefore:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

places `Authentication` into the **current** context, which does not mean it was written to `HttpSession`. Without saving, a new `GET /api/me` request can still appear anonymous.

### Persisting Across Requests with saveContext(...)

`SecurityContextRepository` has the method:

~~~java
void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

This is a conceptual signature illustrating the contract, not a complete source file. When you have a valid `Authentication` and appropriate repository:

~~~java
repository.saveContext(context, request, response);
~~~

Then subsequent requests (sending the right cookie) can reload the context from the same repository.

Implementations to know:

| Repository | Usage |
| --- | --- |
| HttpSessionSecurityContextRepository | Stores SecurityContext in HTTP session; suited for cookie-based browser logins |
| RequestAttributeSecurityContextRepository | Holds context in request attributes; useful across servlet dispatches of the same request, does **not** persist login across requests |
| DelegatingSecurityContextRepository | Combines multiple repositories, commonly request attributes and HttpSession |
| NullSecurityContextRepository | Does not persist context; suited for certain stateless flows |

The example below uses **DelegatingSecurityContextRepository**, combining `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`, supporting both in-request dispatches and session persistence.

### Why Does Spring Security 6 Emphasize Explicit Save?

In Spring Security 6's architecture, `SecurityContextHolderFilter` typically handles only **loading** the context and clearing the holder, instead of implicitly detecting every mutation and auto-saving at the end of the request as some legacy `SecurityContextPersistenceFilter` paths did. Thus, when writing custom authentication filters, you must actively ensure `SecurityContextRepository.saveContext(...)` is called at the right time.

Standard authentication filters can handle saving automatically. With **AbstractAuthenticationProcessingFilter**, you configure the repository on the filter and the framework saves context during `successfulAuthentication(...)`. Never assume a controller snippet merely calling `SecurityContextHolder.setContext(...)` preserves login across requests.

**Important:** the repository attached to the custom login filter and the repository configured on `HttpSecurity`'s security context must match. If login saves to repo A while the next request's `SecurityContextHolderFilter` loads from repo B, the user appears unauthenticated.

## 5. Step Three: SessionAuthenticationStrategy Protects Sessions at Login

`SessionAuthenticationStrategy` is invoked **when an authentication attempt succeeds**, not on every request that already has a session. It can represent one or more policies:

- **ChangeSessionIdAuthenticationStrategy:** rotates the existing session's ID after authentication to mitigate session fixation. It does not replace saving `SecurityContext`.
- **CsrfAuthenticationStrategy:** clears the old CSRF token after successful authentication so the client obtains a fresh token per configuration.
- **ConcurrentSessionControlAuthenticationStrategy:** limits concurrent logins per policy; requires `SessionRegistry` and complete setup.
- **RegisterSessionAuthenticationStrategy:** registers the session with `SessionRegistry` for session concurrency tracking.
- **CompositeSessionAuthenticationStrategy:** executes a sequence of strategies in an explicit order.

Spring Security can provide session strategies assembled by standard configurers. However, **a custom filter does not automatically receive all expected strategies** if instantiated with `new` and added to the chain. Configure or pass the right `SessionAuthenticationStrategy` to your custom filter.

### Session Fixation Protection vs Creating a New Session

Suppose the browser already holds a `JSESSIONID` from fetching a CSRF token before login. After successful login, the session fixation strategy can rotate the **session ID**. Valid session data is preserved per container mechanisms, while the client must receive and send the updated cookie.

Do not save an old `JSESSIONID` and reuse it on subsequent requests after the server rotates the ID. Regular browsers accept the new `Set-Cookie`; with curl or HTTP clients, maintain a cookie jar.

Session fixation protection **does not automatically limit an account to a single session**. For concurrency control, attach the corresponding strategies and `SessionRegistry` or session-tracking mechanism; calling `changeSessionId` alone does not cap device count.

### Refreshing the CSRF Token After Authentication

For cookie-session apps, we explicitly invoke `CsrfAuthenticationStrategy` after handling the session ID. This invalidates/removes the previous CSRF token from the repository per strategy logic. Clients should call `GET /csrf` again after login before making subsequent POSTs (such as logout).

If using Spring Security's session management configurer to assemble strategies, verify CSRF/session/concurrency components are all wired. If constructing `CompositeSessionAuthenticationStrategy` manually like this lesson, you are responsible for ordering and adding policies matching your application's requirements.

## 6. SessionCreationPolicy: Cookie-Session and Stateless Are Not the Same

Common policies:

| Policy | Operational Meaning |
| --- | --- |
| ALWAYS | Spring Security may proactively create an HttpSession |
| IF_REQUIRED | Creates a session when needed by an appropriate mechanism; common choice for form/session login |
| NEVER | Spring Security does not proactively create a session, but may use an existing one |
| STATELESS | Spring Security neither creates nor uses HttpSession to obtain SecurityContext; design typically requires authenticating every request via tokens or another mechanism |

For **JSON login persisting SecurityContext in a session**, the example uses **IF_REQUIRED** paired with `HttpSessionSecurityContextRepository`. If you simultaneously set `sessionCreationPolicy(STATELESS)`, set `NullSecurityContextRepository`, or drop cookies between requests, you cannot expect "after POST login, subsequent GET stays authenticated via session".

### JSON Does Not Mean JWT

"The client sends JSON" describes only the **request body format**. It does not decide whether login state uses cookie-sessions or Bearer tokens.

- JSON login + session cookie: server stores `SecurityContext`/`Authentication` and issues a session cookie; follow-up requests send the cookie, with CSRF protection for browsers.
- JSON login + JWT: server typically returns a signed access token; client sends Bearer tokens on follow-up requests; resource server re-verifies the token without using a session to store `SecurityContext`.
- JSON login + opaque token: depends on token store/introspection mechanisms.

This lesson implements only the **session-cookie** model. Never copy saving `SecurityContext` into `HttpSession` into a strictly stateless JWT architecture without clear intent.

## 7. Complete Hands-On Project: JSON Login with Session and CSRF

We use Spring Boot 3.3.5, Spring Security 6.x managed by Spring Boot, Java 17, Spring MVC, and Jackson. Login runs through a custom filter **extending AbstractAuthenticationProcessingFilter**. We choose this superclass because it provides the built-in flow: `attemptAuthentication` → session strategy → `successfulAuthentication`/`unsuccessfulAuthentication` and success/failure handlers.

Application endpoints:

- `GET /csrf` is public and issues a CSRF token for browsers to send with cookies.
- `POST /api/login` accepts JSON with username/password and a CSRF header, authenticating via `AuthenticationManager`.
- `GET /api/me` requires login, relying on the `SecurityContext` saved in the session.
- `POST /api/logout` clears the session and returns HTTP 204; clients need a fresh CSRF token after logging in.
- `GET /api/me` before login returns 401 without redirecting to an HTML UI.
- No `formLogin`, no HTTP Basic, and no JWTs are used in the demo.

### 7.1. Project Structure

~~~text
json-session-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (if using Gradle Wrapper)
  src/main/java/dev/example/jsonsession/
    JsonSessionApplication.java
    JsonLoginFilter.java
    SecurityConfig.java
    ApiController.java
  src/test/java/dev/example/jsonsession/
    JsonSessionIntegrationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'json-session-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The application requires a project with a matching Gradle Wrapper; if generated via Spring Initializr, the Gradle Wrapper is usually included. Otherwise, use an installed Gradle or generate the wrapper first. **Do not run javac on a single standalone file**, as the example uses Spring and Jackson classes from the build-tool-managed classpath.

### 7.2. Main Class

File `src/main/java/dev/example/jsonsession/JsonSessionApplication.java`:

~~~java
package dev.example.jsonsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonSessionApplication.class, args);
    }
}
~~~

### 7.3. Custom JSON Login Filter

File `src/main/java/dev/example/jsonsession/JsonLoginFilter.java`:

~~~java
package dev.example.jsonsession;

import java.io.IOException;
import java.util.Locale;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class JsonLoginFilter extends AbstractAuthenticationProcessingFilter {

    private final ObjectMapper objectMapper;

    public JsonLoginFilter(AuthenticationManager manager, ObjectMapper mapper) {
        super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        this.objectMapper = mapper;
    }

    public record LoginBody(String username, String password) {
    }

    @Override
    public Authentication attemptAuthentication(
            HttpServletRequest request,
            HttpServletResponse response)
            throws AuthenticationException, IOException {

        String contentType = request.getContentType();

        if (contentType == null
                || !contentType.toLowerCase(Locale.ROOT)
                        .startsWith("application/json")) {
            throw new BadCredentialsException("Invalid login request");
        }

        LoginBody body;
        try {
            body = objectMapper.readValue(
                    request.getInputStream(), LoginBody.class);
        } catch (JsonProcessingException invalidJson) {
            throw new BadCredentialsException(
                    "Invalid login request", invalidJson);
        }

        if (body == null
                || body.username() == null
                || body.username().isBlank()
                || body.password() == null) {
            throw new BadCredentialsException("Invalid login request");
        }

        UsernamePasswordAuthenticationToken token =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        body.username(), body.password());

        return getAuthenticationManager().authenticate(token);
    }
}
~~~

Analysis:

1. **AntPathRequestMatcher("/api/login", "POST")** ensures the filter processes only POST login. Other endpoints flow through the chain normally.
2. Jackson `ObjectMapper` parses the body into a Java record, avoiding manual string splitting or regex.
3. Content-Type and required fields are checked before authenticating. The example maps all malformed JSON/request errors to `BadCredentialsException` so the failure handler returns a **generic 401**; production can separate 400/415 statuses with dedicated validation without leaking credentials.
4. `UsernamePasswordAuthenticationToken.unauthenticated(...)` creates an **unauthenticated** token for `AuthenticationManager` to verify, without setting `authenticated=true`.
5. This filter does **not** set `SecurityContextHolder` inside `attemptAuthentication`; the superclass runs the session strategy and saves the context in the success branch **when configured with the right repository**.
6. Because `JsonLoginFilter` is instantiated with `new`, it is not a bean auto-registered by the container as a Servlet Filter; it is attached to `SecurityFilterChain` via `HttpSecurity.addFilterBefore`. This prevents a common double-registration bug.

The filter reads the request body and stores neither username nor password in shared mutable fields across threads. The raw password lives only as long as needed to authenticate; never log bodies or tokens.

### 7.4. SecurityConfig: Wiring Both Repository and Session Strategy

File `src/main/java/dev/example/jsonsession/SecurityConfig.java`:

~~~java
package dev.example.jsonsession;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("local-pass-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationConfiguration authenticationConfiguration,
            ObjectMapper objectMapper) throws Exception {

        // Spring Security configuration's manager uses UserDetailsService
        // and PasswordEncoder above. Avoid self-marking tokens authenticated.
        AuthenticationManager manager =
                authenticationConfiguration.getAuthenticationManager();

        // Shared repository to save on login and reload on subsequent requests.
        SecurityContextRepository contextRepository =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository());

        // Same CSRF repository for CsrfFilter and post-login strategy.
        HttpSessionCsrfTokenRepository csrfRepository =
                new HttpSessionCsrfTokenRepository();

        // Session fixation protection and clearing CSRF token after login.
        SessionAuthenticationStrategy sessionStrategy =
                new CompositeSessionAuthenticationStrategy(List.of(
                        new ChangeSessionIdAuthenticationStrategy(),
                        new CsrfAuthenticationStrategy(csrfRepository)));

        JsonLoginFilter jsonFilter = new JsonLoginFilter(manager, objectMapper);

        // Two core lines: custom filter must be wired with both mechanisms.
        jsonFilter.setSessionAuthenticationStrategy(sessionStrategy);
        jsonFilter.setSecurityContextRepository(contextRepository);

        jsonFilter.setAuthenticationSuccessHandler(
                (request, response, authentication) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                            StandardCharsets.UTF_8.name());
                    objectMapper.writeValue(
                            response.getWriter(),
                            Map.of("status", "authenticated"));
                });

        jsonFilter.setAuthenticationFailureHandler(
                (request, response, exception) -> {
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                            StandardCharsets.UTF_8.name());
                    objectMapper.writeValue(
                            response.getWriter(),
                            Map.of("error", "invalid_credentials"));
                });

        http
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .securityContext(security -> security
                        .securityContextRepository(contextRepository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .requestCache(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/login")
                        .permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(
                                (request, response, exception) ->
                                        response.sendError(
                                                HttpServletResponse.SC_UNAUTHORIZED)))
                .logout(logout -> logout
                        .logoutUrl("/api/logout")
                        .logoutSuccessHandler(
                                (request, response, authentication) ->
                                        response.setStatus(
                                                HttpServletResponse.SC_NO_CONTENT)));

        http.addFilterBefore(jsonFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
~~~

Key points of the configuration:

**(a) AuthenticationManager:** `AuthenticationConfiguration.getAuthenticationManager()` uses the authentication setup assembled by Spring Security for the application—in the example, the in-memory `UserDetailsService` and `PasswordEncoder`. When substituting a custom `AuthenticationManager` or `AuthenticationProvider`, ensure the new manager is wired into `JsonLoginFilter`.

**(b) Context repository:** the exact same `contextRepository` instance is passed to **SecurityContextHolderFilter/HttpSecurity** and **JsonLoginFilter**. On login success, `AbstractAuthenticationProcessingFilter` saves the result via its configured repository; `GET /api/me` later reloads it via the security context config. `DelegatingSecurityContextRepository` supports both request attributes and HTTP sessions.

**(c) Session strategy:** `CompositeSessionAuthenticationStrategy` executes `ChangeSessionIdAuthenticationStrategy` followed by `CsrfAuthenticationStrategy`. These two policies fit session-based JSON login; they do not automatically enforce concurrent-session limits. If the app enables `maximumSessions` or `SessionRegistry`, integrate the corresponding session-management strategies and filters properly rather than copying this short composite alone.

**(d) SessionCreationPolicy.IF_REQUIRED:** allows creating and using `HttpSession` when needed. Switching to `STATELESS` while expecting session login is contradictory.

**(e) CSRF:** `HttpSessionCsrfTokenRepository` binds CSRF tokens to the session. `POST /api/login` and `POST /api/logout` must send a valid token. `CsrfAuthenticationStrategy` removes the old token upon success, so clients must fetch a fresh one before subsequent POSTs.

**(f) Authorization:** `GET /csrf` and `POST /api/login` are open at the authorization layer; all other endpoints require authentication. `permitAll` does **not** disable `CsrfFilter`. `POST /api/login` still requires a CSRF token because CSRF is a separate filter.

**(g) HTTP semantics:** 401 is returned by the entry point when an unauthenticated request hits a protected endpoint; failed POST login also returns 401 via the failure handler; missing CSRF tokens typically return 403 from `CsrfFilter`; successful login returns 200 JSON; successful logout returns 204.

**(h) Filter order:** `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the JSON filter at a known chain position, after the CSRF filter in typical ordering. The `UsernamePasswordAuthenticationFilter` class serves as a Spring Security ordering anchor even when `formLogin` is disabled in this chain. The filter will not run in other chains if the app has multiple `SecurityFilterChain`s and the filter is attached only here.

**(i) Request cache:** the demo disables `requestCache` because the API returns JSON 401 instead of relying on saved-request redirects. Hybrid HTML web apps may need a different strategy.

**(j) Logout:** configures a dedicated logout URL for JSON clients, returning 204 instead of redirecting. `LogoutFilter` handles logout, session invalidation, and clearing `SecurityContext` by default. Clients must update cookies and clear UI login state; never return session IDs in response bodies.

### 7.5. GET /csrf and the Protected Endpoint

File `src/main/java/dev/example/jsonsession/ApiController.java`:

~~~java
package dev.example.jsonsession;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken());
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

Spring MVC can receive `CsrfToken` attached to the request by Spring Security and pass it into the controller. Calling `getToken()` materializes the token under Spring Security 6's deferred token mechanism. `headerName` tells the client which header to send; with `HttpSessionCsrfTokenRepository` it is typically `X-CSRF-TOKEN`.

In environments using `XorCsrfTokenRequestAttributeHandler` by default, the token exposed to browsers may be masked against BREACH; send **the exact token returned by the endpoint** in the header rather than sending or comparing raw tokens read from internal sessions. When swapping CSRF repositories/handlers, re-verify the client-server contract.

The `GET /csrf` route is an **intentionally** public API bound to the session. Never return `Authentication`, `JSESSIONID`, passwords, or session attributes to the frontend. Apply appropriate rate limits/caching; tokens must not be logged.

`GET /api/me` simply receives `Authentication` supplied by Spring MVC; when unauthenticated, `authorizeHttpRequests` blocks the request and the entry point returns 401.

### 7.6. Running the Project

In the directory containing the Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell, the equivalent commands are typically:

~~~powershell
./gradlew.bat test
./gradlew.bat bootRun
~~~

Once Boot runs on default `localhost:8080`, you can test with a same-origin browser or HTTP tool. Example curl commands with a cookie jar in an environment with `jq`:

~~~bash
# Step 1: fetch CSRF token and keep initial session cookie.
curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq .

# Step 2: store token in variable (also keeping cookie).
TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

# Step 3: authenticate, receive/update cookie after login.
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -d '{"username":"learner","password":"local-pass-123"}' \
  http://localhost:8080/api/login

# Step 4: subsequent request using the new cookie.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/me
~~~

The sample commands target Bash/POSIX shells with `jq`; on Windows PowerShell, variable syntax, line continuation, and JSON escaping differ. The cookie jar **cookies.txt contains session state**, so keep it secret, delete it safely after testing, and never commit it to Git.

Expected results (highlighting key outputs, not a byte-for-byte HTTP response):

~~~text
GET /csrf:
  HTTP 200, JSON with headerName and token

POST /api/login (valid credentials and CSRF):
  HTTP 200
  {"status":"authenticated"}

GET /api/me (sending updated session cookie):
  HTTP 200
  {"username":"learner"}

GET /api/me (without cookie or invalid session):
  HTTP 401
~~~

Do not hardcode or directly compare `JSESSIONID` values; the container may rotate the session ID after login, and `Set-Cookie` headers carry `HttpOnly`, `Secure`, `SameSite`, or `Path` attributes depending on configuration. A cookie jar lets the client track the active ID automatically.

**The password `local-pass-123` is only for local demos**—never use it in production. Production requires HTTPS, login attempt rate limiting, and keeping session data out of logs/URLs.

### 7.7. Logging Out with a Fresh CSRF Token

After successful login, `CsrfAuthenticationStrategy` may clear the initial token. Clients should call `GET /csrf` again before `POST /api/logout`:

~~~bash
NEW_TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  -H "X-CSRF-TOKEN: $NEW_TOKEN" \
  http://localhost:8080/api/logout
~~~

Logout is expected to return `204 No Content`. A `GET /api/me` request using the logged-out session (once the cookie/session is invalidated) returns 401. Real applications must synchronize frontend state rather than merely clearing a JavaScript variable and assuming the server logged out.

### 7.8. Integration Testing with MockMvc

File `src/test/java/dev/example/jsonsession/JsonSessionIntegrationTest.java`:

~~~java
package dev.example.jsonsession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonSessionIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void csrfTokenCanBeFetchedWithoutLoggingIn() throws Exception {
        mvc.perform(get("/csrf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
                .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    void protectedEndpointRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jsonLoginPersistsAuthenticationAcrossRequests() throws Exception {
        MvcResult login = mvc.perform(
                        post("/api/login")
                                .with(csrf())
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("""
                                        {
                                          "username": "learner",
                                          "password": "local-pass-123"
                                        }
                                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("authenticated"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void invalidCredentialsDoNotAuthenticate() throws Exception {
        mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "wrong-password"
                                }
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void malformedJsonIsRejectedByFailureHandler() throws Exception {
        mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{invalid-json"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void missingCsrfTokenFailsBeforeJsonAuthentication() throws Exception {
        mvc.perform(post("/api/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "local-pass-123"
                                }
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void jsonLogoutReturnsNoContent() throws Exception {
        MvcResult login = mvc.perform(post("/api/login")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "username": "learner",
                                  "password": "local-pass-123"
                                }
                                """))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }
}
~~~

**Significance of the key test:** receiving HTTP 200 on `POST /api/login` **is not enough**. `jsonLoginPersistsAuthenticationAcrossRequests` grabs the login request's `HttpSession` and sends **a separate `GET /api/me` request**; only when `SecurityContext` was properly saved and reloaded does the controller return username `learner`.

`spring-security-test`'s `csrf()` simulates a valid token; it does not by itself verify token/cookie lifecycles in a real browser. For production frontends, add tests using a real HTTP browser covering pre- and post-`changeSessionId` sessions, fresh post-login tokens, CORS, and `SameSite`.

If you change response policies, matchers, CSRF handlers, namespaces, or context paths, update tests to match the application's API contract rather than deleting assertions to bypass failures.

## 8. What If Writing a Custom OncePerRequestFilter or JSON Controller?

`AbstractAuthenticationProcessingFilter` avoids manually assembling the lifecycle. However, some projects use a custom `OncePerRequestFilter`, a `@PostMapping` controller, or `AuthenticationFilter`/`AuthenticationConverter`. Those extension points work **provided you fulfill every responsibility**.

Once the manager returns a verified `Authentication`, the core logic must be equivalent to:

~~~java
// Snippet inside a handler/filter with valid request/response,
// manager, and sessionStrategy/repository; not a standalone file.
Authentication authenticated =
        authenticationManager.authenticate(loginToken);

// 1. Session policy must run in the successful authentication branch.
sessionStrategy.onAuthentication(
        authenticated, request, response);

// 2. Create a new context instead of mutating a shared old context object.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// 3. Save before response commits so cookie/session can be updated.
securityContextRepository.saveContext(
        context, request, response);

// 4. Only then write 200 JSON; do not include password/token in body.
~~~

This function shows **the order of responsibilities**, not a guaranteed drop-in replacement for all logic in a framework authentication filter: custom code must also handle `AuthenticationException`, clear context on errors, session exceptions, remember-me if enabled, events, redirects or response commits, CSRF protection, correlation/auditing, and concurrency control.

If authenticating in a `@RestController`, invoking `sessionStrategy`/`repository` manually as above can be necessary. **Do not confuse the response sending `Set-Cookie` with `SecurityContext` having been saved:** a session cookie can appear simply because CSRF or another feature created a session prior to login.

### Why Does Order Matter?

Calling `saveContext` before running the session strategy can cause session fixation/cookie issues depending on the servlet container and repository. With `AbstractAuthenticationProcessingFilter`, the framework manages the order consistently. If writing it yourself, apply the session strategy after successful authentication and then create/set/save `SecurityContext` before the response commits.

If `SessionAuthenticationStrategy` throws `SessionAuthenticationException`, this is not a completed success branch. Do not proceed to save `Authentication` and return 200 as logged in. Verify session validity and respond per policy.

### Can You Just Call request.getSession().setAttribute(...)?

Do not set an arbitrary attribute like `"username"` and assume Spring Security will recognize the user. `SecurityContextHolderFilter` loads context per `SecurityContextRepository`'s contract, using specific keys and procedures. Calling `saveContext(...)` on the right repository is the proper, compatible API.

### Can the Session ID Be Returned in JSON?

No. The session ID is a secret acting as a bearer credential in cookie-session models. Let the browser/container transmit cookies via `Set-Cookie` and `Cookie` per HTTP, with `HttpOnly`/`Secure`/`SameSite` configured appropriately; never expose `JSESSIONID` in JSON or URLs.

## 9. Upgrading Session Strategy When Concurrent Session Limits Apply

The example uses `ChangeSessionIdAuthenticationStrategy` and `CsrfAuthenticationStrategy`, **without enabling `maximumSessions`**. If your product requires one session per user or device limits, full concurrency control is required.

An assembled strategy may include:

~~~text
Authentication succeeds
    |
ConcurrentSessionControlAuthenticationStrategy
    |
ChangeSessionIdAuthenticationStrategy
    |
RegisterSessionAuthenticationStrategy
    |
CsrfAuthenticationStrategy (per configuration requirement)
    |
SecurityContextRepository.saveContext(...)
~~~

This is a **conceptual model**, not copy-paste code to enable concurrency control. When using `SessionRegistry`, `ConcurrentSessionFilter`, and session-destroyed listeners, ordering/registration and marking expired sessions must be consistent.

- `ConcurrentSessionControlAuthenticationStrategy` needs a suitable `SessionRegistry` to check active sessions.
- `RegisterSessionAuthenticationStrategy` must register the new session once policy allows.
- `ConcurrentSessionFilter` can act on expired session state per concurrency configuration.
- `SessionRegistryImpl` for single-node apps differs from multi-node setups. Across multiple nodes, you need a distributed session store and consistent session tracking policies.
- If a custom filter fails to invoke the strategy configured on the chain, `maximumSessions` in the DSL may **not apply to custom JSON login** even when standard form login behaves as expected.

A less error-prone approach for complex session concurrency is packaging the custom filter as a `SecurityConfigurer`, retrieving the session strategy built by `HttpSecurity` at the proper `configure` stage, attaching it to the filter, and writing tests for `maximumSessions`. Never grab a shared object too early and assume it is already fully assembled.

## 10. CSRF, Cookies, CORS, and SPA Clients

### 10.1. Why Must JSON POSTs with Cookies Still Care About CSRF?

JSON does not prevent attackers from abusing session cookies; browsers send cookies per origin/`SameSite` rules. If cookies accompany unintended requests, session-based apps can face CSRF—especially with misconfigured CORS/`SameSite` or endpoints accepting requests easily triggered from external pages.

For JSON login **using cookies to maintain authentication**, safe policy keeps CSRF protection enabled. The demo reads `X-CSRF-TOKEN` from headers using the token from `GET /csrf`. Never disable CSRF merely because the frontend is an SPA or to make Postman/curl requests easier.

### 10.2. Cookies Are Necessary but Not Sufficient

Clients must preserve a valid session cookie and update it after session fixation protection. In same-origin frontend `fetch`, `credentials` defaults to `same-origin`; for cross-origin, evaluate `credentials: "include"`, `Access-Control-Allow-Credentials`, and actual CORS config.

**Never use `Access-Control-Allow-Origin: *` with credentialed requests.** Whitelist allowed origins, require HTTPS, and review `SameSite`/`Secure` cookies. CORS only governs what browsers allow frontends to read/send by policy; it does not replace authentication, CSRF, or session security.

### 10.3. Session Store, Clusters, and Load Balancers

`HttpSession` may reside in a single node's memory. If login hits instance A while the next request hits B without a shared session store or appropriate sticky sessions, `SecurityContext` will not load as expected.

In multi-node apps, consider Spring Session/Redis or a properly operated distributed session system, addressing session serialization, timeouts, concurrency, and revocation. Calling `saveContext(...)` in Java does not solve session replication infrastructure.

### 10.4. CSRF Tokens After Login

In the demo, `CsrfAuthenticationStrategy` invalidates the old token. A client can log in with token A, then must call `GET /csrf` to obtain token B before sending further POSTs. Keeping token A can trigger 403 on logout or data mutations even though the session cookie is valid. That is the difference between **having valid authentication** and **a state-changing request passing CSRF**.

## 11. Common Mistakes and How to Fix Them

### Mistake 1: POST /api/login Returns 200 Yet GET /api/me Still Returns 401

**Common causes:** only calling `SecurityContextHolder.setContext` without `saveContext`; login repository and `SecurityContextHolderFilter` repository mismatch; session cookie not preserved/updated; `SessionCreationPolicy.STATELESS`; expired session or routed to a different node.

**Fix:** verify `AuthenticationManager` actually returns authenticated, `saveContext` runs before response commit, the same repository is shared, browser sends the updated cookie, session store holds the data, and the follow-up GET hits the right chain.

### Mistake 2: Rotating Session ID Manually Without Saving Authentication

`ChangeSessionIdAuthenticationStrategy` handles session fixation, **not saving SecurityContext**. You still must invoke `repository.saveContext` (or let `AbstractAuthenticationProcessingFilter` save via its configured repository).

### Mistake 3: Saving Context Only, Skipping Session Strategy

Login may appear to succeed and persist, yet lacks session fixation protection or policy-mandated CSRF rotation. When using custom authentication filters, attach appropriate strategies and test them.

### Mistake 4: Using NullSecurityContextRepository or STATELESS for Cookie Login

`NullSecurityContextRepository` does not persist across requests. `STATELESS` does not use `HttpSession` to load `SecurityContext`. If cookie-session is the goal, choose aligned policies. If genuinely stateless, clients must send a token every request and the framework must verify it in the right filter.

### Mistake 5: Missing CSRF Token and Concluding Wrong Password

`POST /api/login` without a token is typically rejected with 403 by `CsrfFilter` before parsers/filters/managers check credentials. Call `GET /csrf`, send the `Cookie` and header from the response. Distinguish 401 (credentials/authentication) from 403 (CSRF/access denied) by origin.

### Mistake 6: Right After Logging In, POST /api/logout Returns 403

`CsrfAuthenticationStrategy` rotates/clears the token after authentication; clients must fetch a new token before the next POST. Do not disable this feature just to make logout tests pass.

### Mistake 7: Custom Filter Does Not Run Because of securityMatcher

`FilterChainProxy` picks the **first matching `SecurityFilterChain`** by `@Order`. If `POST /api/login` falls outside the chain containing `JsonLoginFilter`, a correct filter matcher will not help. Check both the chain's `securityMatcher` and the filter's request matcher. A broad fallback chain protects URLs outside specialized chains.

### Mistake 8: Annotating the Filter as @Component and Adding It to the Chain

A `Filter` bean can be auto-registered by Boot into the Servlet container, then registered again inside Spring Security's chain. That runs the filter twice or out of order. In the demo, the filter is created with `new` inside `SecurityConfig` and added only to `HttpSecurity`, without `@Component`.

### Mistake 9: Creating a New SecurityContext Yet Forgetting to Save Before Commit

Once the response commits, writing cookies or session data can fail depending on container/repository. Run the full filter lifecycle before the success handler sends JSON/status.

### Mistake 10: Assuming Login Success Automatically Enables Concurrency Control

The short composite of `ChangeSessionId` and `CsrfAuthenticationStrategy` does not limit concurrent sessions. Configuring `maximumSessions` requires `SessionRegistry`/concurrent session tracking, corresponding strategies, and integration tests. Do not infer it from HTTP 200.

### Mistake 11: Authenticating in a Controller Yet Manually Creating authenticated=true

Never bypass `AuthenticationManager`/`Provider` to grant permissions directly from request JSON. Client-sent username/roles are untrusted. Attach only an `Authentication` returned by a trusted verification mechanism.

### Mistake 12: Logging Full JSON Requests, Authorization Headers, or Cookies

Login requests contain passwords, CSRF tokens, and cookies. Never log raw bodies, credentials, `JSESSIONID`, full `SecurityContext`s, or sensitive exception messages. Log safe correlation IDs, outcomes, and generic error codes.

### Mistake 13: Neglecting Session Expiration or Logout

A saved `Authentication` does not keep a session alive forever. On expiration, browsers receive 401 and must start a new login. Logout requires server-side invalidation and context clearing; UIs must clear displayed auth state. Never replay old cookies as a way to "restore" sessions.

### Mistake 14: Returning Session Cookies in JSON or URLs

Never return `JSESSIONID`, session tokens, or secrets in JSON, URL queries, or `localStorage`. Prefer `HttpOnly`/`Secure`/`SameSite` cookies over HTTPS with appropriate session expiry and CSRF protection.

## 12. QA and Production Testing Matrix

| Case | Demo Expectation | What to Verify |
| --- | --- | --- |
| GET /csrf anonymous | 200 + token | Token belongs to the right session/cookie |
| GET /api/me anonymous | 401 | No user data leaked |
| POST /api/login valid JSON + CSRF | 200 JSON | AuthenticationManager succeeds |
| GET /api/me right after login + new cookie | 200 username | SecurityContext saved and reloaded |
| GET /api/me after login, no cookie | 401 | Thread context not confused with session |
| POST /api/login wrong password + CSRF | 401 generic JSON | No authenticated context saved |
| POST /api/login malformed JSON + CSRF | 401 in demo | No parser/stack trace leaked |
| POST /api/login missing CSRF | 403 | Blocked before authentication step |
| POST /api/logout + new CSRF token | 204 | Session invalidated / context cleared |
| GET /api/me after logout | 401 | Old session unusable |
| Existing session before login | Session ID rotates when applicable | Session fixation prevented |
| Two concurrent requests to app | Each request gets its own context | No cross-thread/state corruption |
| Routing to another server instance | Still works if session shared | Session replication / distributed store |
| `/api/**` chain and another chain | Right chain contains login filter | `securityMatcher`, `@Order`, no bypass |

As the system grows, add tests for stale CSRF tokens post-login, session timeouts, concurrent login limits, revoked accounts, `SameSite`/`Secure`/`HttpOnly` cookies, CORS, reverse proxies, session fixation, and persistence. Include end-to-end browser tests verifying cookies are actually saved and transmitted properly.

## 13. Self-Check Questions

**Question 1.** Why does `AuthenticationManager` return a valid `Authentication`, yet `GET /api/me` still returns 401?

> Because the `authenticate` result exists only for the current attempt. If `SecurityContext` is not saved to the `SecurityContextRepository` loaded by subsequent requests, or the browser fails to send the right cookie, the next request remains anonymous.

**Question 2.** Do `SecurityContextHolder.setContext(context)` and `saveContext(...)` have the same effect?

> No. `setContext` populates context in the current thread/strategy; `saveContext` persists data via the repository so future requests can reload it. In Spring Security 6, custom authentication usually requires explicit saving.

**Question 3.** Does `ChangeSessionIdAuthenticationStrategy` save `SecurityContext` by itself?

> No. It addresses session fixation by rotating the existing session's ID when appropriate. Saving `Authentication` belongs to `SecurityContextRepository`.

**Question 4.** If a custom `JsonLoginFilter` extends `AbstractAuthenticationProcessingFilter`, what is the main advantage?

> It provides the standard authentication lifecycle, including `attemptAuthentication`, failure/success handling, session strategy, and context saving via the repository when properly configured—avoiding reimplementing sensitive steps.

**Question 5.** Why do both `HttpSecurity` and `JsonLoginFilter` need the same repository?

> Because login must write to the exact location `SecurityContextHolderFilter` reads from on the next request. Using incompatible repositories loses login state.

**Question 6.** If using `POST /api/login` with `Content-Type: application/json`, can CSRF be omitted?

> Do not assume so. JSON is only a data format; cookie-session browsers still require CSRF evaluation. The example includes CSRF protection and the `X-CSRF-TOKEN` header.

**Question 7.** Login succeeded, yet `POST` logout returns 403. Why?

> `CsrfAuthenticationStrategy` may have cleared the old token after login. The client must call `GET /csrf` to obtain a fresh token for the current session before `POST` logout.

**Question 8.** Are `SessionCreationPolicy.STATELESS` and `HttpSessionSecurityContextRepository` compatible for persisting sessions?

> No. `STATELESS` is designed not to rely on `HttpSession` to maintain `SecurityContext`. For cookie-session flows, use a session-permitting policy such as `IF_REQUIRED`.

**Question 9.** Why can't sending JSON `{"username":"admin","roles":["ADMIN"]}` self-grant the `ADMIN` authority?

> Because client data is untrusted; authorities must be verified by `AuthenticationProvider`/`Manager` or loaded from a trusted server source.

**Question 10.** Why can login succeed on a dev machine yet subsequent requests in a cluster return 401?

> If sessions live in node A's memory, a request routed to node B cannot see that session. Proper session infrastructure or consistent routing is required alongside code actually calling `saveContext`.

**Question 11.** When must `ConcurrentSessionControlAuthenticationStrategy` be added?

> When policy requires limiting concurrent sessions and the app has full `SessionRegistry`, session tracking, and registration/expiration configured; it is not enabled merely by rotating session IDs.

**Question 12.** Why not use a `static` variable to store `Authentication` after `POST /api/login`?

> Because all users/requests/threads would share or read corrupted state, causing identity leaks and privilege escalation. Spring Security provides `SecurityContextHolder` per request and repositories per session.

## Summary

**Session-backed JSON login must complete authentication, session handling, and context persistence.**

- `AuthenticationManager` proves credentials are valid.
- `SessionAuthenticationStrategy` enforces session protection policies at the **right moment** (fixation protection, CSRF rotation, concurrency when configured).
- `SecurityContextHolder` holds `Authentication` for current request processing.
- `SecurityContextRepository` persists context so future requests can reload it.
- `SecurityContextHolderFilter` and `SecurityFilterChain` ensure the next request uses the same repository with a valid session cookie.

In Spring Security 6, custom JSON login demands extra care because **calling `setContext` alone does not replace `saveContext`**. Prefer `AbstractAuthenticationProcessingFilter` or an authentication filter with a standard lifecycle to avoid missing steps. If writing a controller/`OncePerRequestFilter` yourself, explicitly wire all responsibilities and test from **POST login through a protected GET on a separate request**.