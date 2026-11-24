# HttpServletRequest.authenticate, login, and logout in Spring Security Servlet

> **Context:** Java 17+, Spring Boot 3.x, and Spring Security 6.x applications using the **Servlet / Spring MVC** model. The three methods `HttpServletRequest.authenticate(HttpServletResponse)`, `login(String, String)`, and `logout()` are Servlet APIs for interacting with a request's authentication state. Spring Security integrates with the Servlet API, but you need to understand who actually handles the call, how `SecurityContext` is maintained, and how these methods differ from standard authentication/logout filters.

## 1. Learning Objectives and Practical Scenario

After this lesson, you will be able to:

- Distinguish **container-managed authentication** from authentication handled by **Spring Security** via `SecurityContextHolderAwareRequestFilter`.
- Explain the inputs, return values, exceptions, and HTTP response side effects of `request.authenticate(response)`.
- Use `request.login(username, password)` when programmatic login is needed and understand why a matching `AuthenticationManager` or authentication mechanism must be configured.
- Understand the scope of `request.logout()`, avoiding confusion between application logout and Identity Provider logout, token revocation, or signing out of all devices.
- Read `request.getUserPrincipal()`, `getRemoteUser()`, and `isUserInRole(...)` after authentication and verify consistency with `SecurityContextHolder`.
- Write a Spring MVC Controller demonstrating all three APIs, test with MockMvc and CSRF, distinguish 302/401/403/204, and avoid credential leaks.

Scenario: an MVC application has an account screen. Users sign in through a standard form, while some legacy features call Servlet APIs inside a controller. Without understanding the integration mechanism, a team might call `request.login(...)` when Spring Security lacks a suitable authentication manager, call `request.logout()` and assume the IdP session also ended, or send both a login redirect and JSON in the same response.

These three methods do not replace the entire authentication infrastructure; they are **standard Servlet entry points** for requesting authentication, logging in, or logging out within the context of an HTTP request.

## 2. Two Ways a Servlet Request Can Be Authenticated

### 2.1. Servlet Container-Managed Authentication

Jakarta Servlet defines these APIs on `jakarta.servlet.http.HttpServletRequest`. When an application server has configured a realm, security constraints, login mechanism, and role mapping, the container can:

1. Authenticate users according to its own policy.
2. Provide `request.getUserPrincipal()`, `getRemoteUser()`, and `isUserInRole(...)`.
3. Execute `request.authenticate(response)` to initiate or continue the configured authentication mechanism.
4. Attempt login with `request.login(username, password)` if supported by the container mechanism.
5. Execute `request.logout()` for the container-managed identity.

Without proper container security configuration, calling these APIs **will not automatically create a login form, user store, or valid passwords**.

### 2.2. Spring Security Wrapping the Request and Integrating the Servlet API

When a request passes through `FilterChainProxy`, Spring Security includes `SecurityContextHolderAwareRequestFilter`. This filter can supply an `HttpServletRequestWrapper` so that Servlet APIs related to the principal and authentication work alongside `SecurityContextHolder`, `AuthenticationManager`, and Spring Security's entry points and logout handlers.

Simplified diagram:

```text
HTTP request
   |
Servlet container
   |
Spring Security FilterChainProxy
   +-- load/prepare SecurityContext
   +-- authentication filters / anonymous / authorization
   +-- SecurityContextHolderAwareRequestFilter
   |        |
   |        +-- Servlet API-compatible request wrapper
   |
DispatcherServlet
   |
@Controller / @RestController
   |
request.authenticate(response) / request.login(...) / request.logout()
   |
Spring Security integration (if the request is properly wrapped)
   |
HTTP response / security context / session
```

**Important:** the same method signature yields different behavior and integration points depending on **the actual request instance passed to the controller**. If an endpoint is excluded from Spring Security via `web.ignoring()`, a custom filter retains the raw request, or the request hits an unexpected filter chain, you cannot assume you received Spring Security's integrated wrapper.

In typical Spring Boot projects with Spring Security, `servletApi` integration is configured in the filter chain by default. When you want to be explicit, you can use `http.servletApi(Customizer.withDefaults())` if supported by your version. Verify with tests on your pinned version rather than guessing from another application server's behavior.

**Do not equate a container principal with a Spring Security principal.** With Spring Security's wrapper, `getUserPrincipal()` reflects the current `Authentication` (excluding anonymous per the wrapper's behavior), whereas an unwrapped `HttpServletRequest` may return a principal from the container realm. When debugging, always check **who supplied the request object**, which chain handled it, and which `SecurityContext` is active.

## 3. Direct Comparison of the Three Methods

| Servlet API | Input | Primary Meaning | Result / Exceptions | What It Does Not Do |
|---|---|---|---|---|
| `boolean authenticate(HttpServletResponse response)` | Current response | Ensure authentication or trigger the configured authentication mechanism | `true` when authenticated; `false` when the process/challenge is incomplete; may throw `IOException`/`ServletException` | Does not prompt for username/password from the controller; does not grant roles or enforce MFA by itself |
| `void login(String username, String password)` | Username and password | Request programmatic authentication using application-received credentials | Returns normally on success; may throw `ServletException` on failure, unsupported mechanism, or invalid state | Does not create users, reset passwords, or enforce MFA policies |
| `void logout()` | No parameters | Request removal of the caller's authentication state in the active request-management mechanism | May throw `ServletException`; session/context effects depend on the integration mechanism | Does not automatically log out all SSO apps, revoke OAuth access tokens, or clear every cookie |

All three methods are **calls with side effects**, not pure getters. `authenticate` may send a redirect or challenge and commit the response; `login` mutates security state; `logout` alters the active state. Never invoke them inside a getter or interceptor just to "check whether the user is logged in".

To merely inspect identity, use getters according to contract:

```java
Principal principal = request.getUserPrincipal();
String username = (principal != null) ? principal.getName() : "anonymous";
boolean admin = request.isUserInRole("ADMIN");
```

The snippet above is illustrative inside a Servlet/controller, not a standalone class. Check role mapping for both the container and Spring Security; in Spring Security, the `ROLE_` convention governs how `isUserInRole(...)` matches against `GrantedAuthority`.

## 4. request.authenticate(response): Proactively Triggering a Challenge

Jakarta Servlet signature:

```java
boolean authenticate(HttpServletResponse response)
        throws IOException, ServletException;
```

### 4.1. States to Distinguish

- **Already has an authenticated identity:** the method can return `true`; only then should the controller continue handling authenticated content.
- **Unauthenticated:** the method invokes the configured authentication mechanism. With form login, the response may be redirected to the login page; with HTTP Basic, the response may be 401 with a `WWW-Authenticate` header; container/IdP mechanisms handle it differently. When a challenge is incomplete, the result is typically `false`.
- **Protocol or integration error:** may throw `IOException` or `ServletException`; never swallow the error and let the request proceed under a `permitAll` rule.
- **Response already handled by the entry point/container:** the controller **must not write additional JSON/HTML**, send a second redirect, or arbitrarily change the status.

Illustrative example inside a controller:

```java
@GetMapping("/session/ensure")
public void ensure(HttpServletRequest request,
                   HttpServletResponse response)
        throws IOException, ServletException {
    if (request.authenticate(response) && !response.isCommitted()) {
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }
    // If false, the authentication mechanism has already handled the challenge.
    // Do not write a body or call sendRedirect here.
}
```

This is a handler method and must live inside a `@Controller` or `@RestController` class with the appropriate imports. The endpoint only illustrates the HTTP contract; real projects usually let Spring Security initiate authentication automatically when protected URLs are accessed rather than calling `authenticate` in every controller.

### 4.2. Why Is 401 Not Always the Default?

An anonymous request to a login-required URL may receive **302** to the login page when using form login, **401** when using HTTP Basic or a bearer token entry point, or another container challenge. `authenticate` has no contract that it "always returns 401"; the status is determined by the authentication entry point.

If `authenticate(response)` returns `false`, do not continue business logic; it does not prove the request is authenticated. Even once authenticated, **authorization still needs checking**: a logged-in user is not automatically allowed on an admin page.

### 4.3. authenticate Is Not a Default MFA Step

Calling `request.authenticate(response)` on an already logged-in session may return `true` without asking the user for a new factor. If your application requires step-up authentication, you must enforce policies checking assurance/authentication age/factors, or force a separate IdP flow and verify the signed result against contract. Never treat calling this API as "re-authenticating with MFA".

## 5. request.login(username, password): Programmatic Login

Signature:

```java
void login(String username, String password) throws ServletException;
```

This is a tool for when an application already has a UI/flow receiving username/password and wants to ask the active authentication mechanism to perform login. It **does not know about user stores, password encoders, or group mappings on its own**; those must be configured in the container or Spring Security.

### 5.1. Reasonable Flow

```text
POST /session/programmatic-login
   |
Over HTTPS only; valid CSRF token if using a browser session
   |
Read username/password from request body (not via URL query)
   |
request.login(username, password)
   |
   +-- failure --> ServletException
   |                 return generic error, do not leak password
   |
   +-- success --> request principal/SecurityContext may be updated
                       according to the active integration mechanism
   |
Check session/security-context persistence and fixation policy
   |
Return 204 or redirect per API contract, without credentials
```

When Spring Security handles the call through its wrapper, credentials can be forwarded to `AuthenticationManager`. Success depends on the configured `AuthenticationProvider`s and proper request wrapping. A filter chain configured solely for OAuth2 login or X.509 **does not automatically** accept username/password via `request.login`.

Avoid calling `request.login` on an already-authenticated request without a clear switch-user/re-authentication design: the Servlet API may reject that state with a `ServletException`, and identity-switching flows must avoid session confusion.

### 5.2. Mandatory Safeguards on Credential-Receiving Endpoints

- **HTTPS and confidentiality:** never use `GET /login?username=...&password=...`; never put credentials in URLs, redirects, exceptions, audits, or HTTP logs.
- **CSRF for browser sessions:** login CSRF matters too; Spring Security typically applies CSRF to POST requests. Do not disable CSRF app-wide just to test POST login/logout.
- **Brute-force / credential-stuffing defenses:** apply rate limiting by identity/IP/device, backoff, anomaly detection, and appropriate lockouts. Spring Security does not replace a full risk engine.
- **Generic error responses:** never reveal whether a username exists or the password was wrong via differing error messages.
- **Session fixation:** verify actual session ID rotation / session authentication strategy policies. Programmatic login is a separate path and must be tested at parity with form login; do not assume every `UsernamePasswordAuthenticationFilter` hook runs.
- **MFA:** a valid username/password only proves the knowledge factor. If a sensitive endpoint requires multiple factors, do not grant immediate access just because `request.login` succeeded.
- **Persist state only when appropriate:** after login, test `SecurityContextRepository`/session persistence on the **next** request; having a principal on the current request does not prove the session remains valid across redirects.

### 5.3. request.login Differs from Manually Setting SecurityContext

These two patterns are **not equivalent**:

```java
// Integrated Servlet/Spring Security mechanism:
request.login(username, password);
```

```java
// Illustrates a design flaw only: performs no authentication at all.
SecurityContextHolder.getContext().setAuthentication(unverifiedAuth);
```

In the second pattern, if `unverifiedAuth` is constructed from client input without `AuthenticationManager` verification, the application can introduce a critical vulnerability. Even with a valid `Authentication`, hand-rolled code must still handle security context persistence, session strategies, failure handling, and auditing. Prefer standard filters/DSL login unless an explicit application requirement calls for programmatic login.

## 6. request.logout(): Which State Does Logout Clear?

Signature:

```java
void logout() throws ServletException;
```

When a request is wrapped by Spring Security with proper servlet integration, `request.logout()` invokes Spring Security's logout logic to clear the authentication context and session state managed by the relevant `LogoutHandler`s. With container-managed security, it asks the container to remove the current identity according to the container's mechanism.

**Never assume a single session/cookie outcome across all implementations.** Empirically verify your version, chain, logout handlers, session repository, and container. In particular:

- **Application session:** Spring Security's default logout handler typically invalidates `HttpSession` and clears `SecurityContext`; custom handlers or unwrapped requests may behave differently.
- **Cookies:** invalidating the server session does not guarantee the browser deletes all custom cookies. You may need `Clear-Site-Data` or explicit cookie deletion (matching path/domain/SameSite) after evaluating side effects.
- **OIDC/SAML SSO:** local logout does not always log out the IdP or other applications. RP-initiated logout or SAML Single Logout must be configured per contract.
- **Bearer tokens:** clearing a browser session does not revoke tokens still valid on other clients; token revocation, expiry, and audience policies must be designed separately.
- **Remember-me / persistent login:** if remember-me is enabled, verify which handler deletes the token and cookie.
- **Sessions on other devices:** logging out the current request does not necessarily invalidate active sessions on other devices.

In Spring Security Servlet, **`POST /logout` handled by `LogoutFilter` is the standard path** when using `logout()` configuration and CSRF. Calling `request.logout()` from a controller is an alternative API choice: use it only when genuinely required by integration or legacy flows. Avoid having two inconsistent logout endpoints (where one clears context while the other leaves remember-me tokens intact).

### 6.1. Why Prefer POST Logout?

Logout is a state-changing operation. Exposing `GET /logout-now` so any page embedding an image or link can trigger logout invites logout CSRF and unintended behavior. For applications using sessions and CSRF protection, require logout via **POST with a valid CSRF token**. Never use `csrf().disable()` just to make curl logout calls simpler.

### 6.2. Controller Logic After Logout

If logout succeeds, return 204 No Content or redirect to a public page. Do not call `getUserPrincipal()` afterward to write user information into the response, since the context may already be cleared. If logout throws `ServletException`, log the event safely and return an appropriate error without leaking tokens, cookies, or credentials.

## 7. Runnable Spring Boot 3.3.x + Spring Security 6.x Example

This example uses **in-memory users** and Spring Security's standard form login. Alongside `/login` and `/logout` managed by standard filters, the app exposes three handlers illustrating the Servlet APIs. This is a local learning demo, **not** a production authentication service; it lacks MFA, user registration, and throttling.

Key point: controllers run **inside the security filter chain**, with `SecurityContextHolderAwareRequestFilter` integration active; the program does not rely on a standalone application server realm.

### 7.1. Structure and Dependencies

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
```

In a project with the Gradle Wrapper, create package `demo.servletapi` and the three classes below.

### 7.2. Main Application

File `src/main/java/demo/servletapi/ServletApiApplication.java`:

```java
package demo.servletapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletApiApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain Configuration

File `src/main/java/demo/servletapi/SecurityConfig.java`:

```java
package demo.servletapi;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${DEMO_PASSWORD}") String demoPassword) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode(demoPassword))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/").permitAll()
                .requestMatchers(HttpMethod.GET, "/session/ensure")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/session/programmatic-login")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/session/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/session/programmatic-logout")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .servletApi(Customizer.withDefaults())
            .build();
    }
}
```

**Explanation:**

- `InMemoryUserDetailsManager` is for demo purposes only. Username `learner` has `ROLE_USER`, and the password is BCrypt-hashed at startup.
- `formLogin` provides form authentication/entry point and the default login page. It does not need to be disabled to use the Servlet API.
- `servletApi` explicitly enables integrating the Servlet request wrapper with Spring Security. Check DSL support for your Spring Security version.
- `/session/programmatic-login` is `permitAll` so unauthenticated users can submit credentials. However, POST requests are still subject to the **CSRF filter**.
- `/session/ensure` is `permitAll` so the controller can proactively call `request.authenticate(response)`. If not logged in, the entry point handles the challenge.
- `/session/me` and the demo logout require a valid principal. There is no blanket `permitAll` rule across `/session/**`.
- Do not call `csrf.disable()`, do not put passwords in query strings, and do not create a default admin user.

### 7.4. Controller Demonstrating All Three APIs

File `src/main/java/demo/servletapi/SessionController.java`:

```java
package demo.servletapi;

import java.io.IOException;
import java.security.Principal;
import java.util.Map;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {
    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/session/me")
    public Map<String, String> me(HttpServletRequest request) {
        Principal user = request.getUserPrincipal();
        return Map.of("user", user.getName());
    }

    @GetMapping("/session/ensure")
    public void ensure(HttpServletRequest request,
                       HttpServletResponse response)
            throws IOException, ServletException {
        if (request.authenticate(response) && !response.isCommitted()) {
            response.setStatus(HttpServletResponse.SC_NO_CONTENT);
        }
        // When false, do not write another body: the entry point has already handled the challenge.
    }

    @PostMapping("/session/programmatic-login")
    public void login(HttpServletRequest request,
                      HttpServletResponse response,
                      @RequestParam String username,
                      @RequestParam String password)
            throws IOException {
        try {
            request.login(username, password);
            response.setStatus(HttpServletResponse.SC_NO_CONTENT);
        } catch (ServletException invalidCredentialsOrState) {
            // Do not return exception details: may leak information.
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication failed");
        }
    }

    @PostMapping("/session/programmatic-logout")
    public void logout(HttpServletRequest request,
                       HttpServletResponse response)
            throws ServletException {
        request.logout();
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }
}
```

**Note:** the login handler in this example only illustrates the API and lacks rate limiting, email verification, auditing, and production accounts. The handler assumes Spring Security has wrapped the request properly and has a username/password-compatible `AuthenticationManager`. If using a container realm instead of Spring Security's request wrapper, behavior may differ; test on your specific setup.

Endpoint `GET /session/me` is protected by `authenticated()`; thus `user.getName()` is only reached after Spring Security lets the request through. In apps with multiple authentication mechanisms, code should guard against a null principal in case chain/dispatch rules change.

### 7.5. Running with Gradle Wrapper

In a Bash environment:

```bash
export DEMO_PASSWORD='a-long-local-demo-password'
./gradlew bootRun
```

Keep demo secrets out of Git. On PowerShell, use the corresponding environment variable syntax rather than copying `export` literally.

Access `http://localhost:8080/`:

```text
public
```

Access `http://localhost:8080/session/me` while unauthenticated: the form login entry point redirects to `/login`. Enter `learner` and the demo password on the standard login page to create a session; `/session/me` will then return JSON with `"user":"learner"`.

To test **programmatic login/logout** over real HTTP, the browser/client must submit a **valid CSRF token bound to the session**. Do not simply POST a password with curl while stripping CSRF; if you receive 403, distinguish a CSRF failure from a login failure. The MockMvc test suite below is the accurate way to verify behavior with CSRF enabled without weakening protections.

## 8. Testing Servlet APIs with MockMvc

Important tests verify that **requests actually traverse Spring Security**, rather than calling controller methods directly with mocks that omit the filter chain. `MockMvc` with `@SpringBootTest` and `@AutoConfigureMockMvc` runs the filter chain in tests; `with(csrf())` simulates a valid CSRF token via `spring-security-test`.

File `src/test/java/demo/servletapi/ServletApiSecurityTest.java`:

```java
package demo.servletapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "DEMO_PASSWORD=local-test-password")
@AutoConfigureMockMvc
class ServletApiSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk());
    }

    @Test
    void authenticateCanStartFormLoginChallenge() throws Exception {
        mvc.perform(get("/session/ensure"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "learner", roles = "USER")
    void authenticatedRequestHasPrincipal() throws Exception {
        mvc.perform(get("/session/me"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void loginRequiresCsrfEvenWhenEndpointPermitsAnonymous() throws Exception {
        mvc.perform(post("/session/programmatic-login")
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void programmaticLoginCreatesUsableSession() throws Exception {
        MvcResult login = mvc.perform(post("/session/programmatic-login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/session/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("learner"));
    }

    @Test
    void logoutClearsCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/session/programmatic-login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-test-password"))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/session/programmatic-logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
    }
}
```

Run:

```bash
./gradlew test
```

**Test scope:** `@WithMockUser` only checks principal/authorities within that test request; it **does not verify the password encoder or real login mechanism**. The `programmaticLoginCreatesUsableSession` test verifies credentials against the in-memory store and checks session state on the subsequent request. The logout test confirms session invalidation **under the example's default configuration**, without guaranteeing identical behavior for every container or custom logout handler.

For projects that swap `SecurityContextRepository`, run multiple chains, add custom filters, or configure stateless sessions or an IdP, update tests to reflect the new security contract. A passing MockMvc test **does not replace** E2E testing with a real browser, cookie flags, TLS/reverse proxies, and IdP logout.

## 9. Comparing Login/Logout Approaches in Spring MVC

| Approach | Entry Point | When to Use | Important Caveats |
|---|---|---|---|
| `request.authenticate(response)` | Servlet API | Controller/Servlet needs to require authentication now | Triggers entry point if unauthenticated; may commit response |
| `request.login(username,password)` | Servlet API | Legacy MVC / programmatic login with username/password | Requires backend authentication manager/realm; caller must handle credentials safely |
| `request.logout()` | Servlet API | Programmatic logout integration on a wrapped request | Must test session handlers, external IdP, and cookies |
| `formLogin()` + default `POST /login` | `UsernamePasswordAuthenticationFilter` | Standard browser form login | Spring Security manages failure, success, session strategy/redirect, and CSRF per config |
| `logout()` + default `POST /logout` | `LogoutFilter` | Standard browser logout | `LogoutHandler`s, logout success handler, and CSRF work together consistently |
| `oauth2Login()` | OIDC/OAuth2 client filters | Browser sign-in with an IdP | Do not accept IdP passwords via `request.login`; local logout differs from SSO logout |
| `saml2Login()` | SAML2 service provider | Enterprise SAML SSO | Requires separate SAML response verification, metadata, and Single Logout |
| `oauth2ResourceServer()` | Bearer token filter | Stateless API | Does not rely on web MVC session login/logout |
| Container realm + Servlet API | Container security machinery | App deployed on an app server with a configured realm | Container principal/roles must be properly trusted/mapped; Spring Security wrapper may not be the primary auth layer |

Do not deploy multiple parallel login/reset/logout endpoints **without a unified policy**. For example, if an app uses OIDC, adding a new endpoint that accepts passwords via `request.login` could accidentally create a backdoor that bypasses IdP MFA.

### 9.1. getUserPrincipal and isUserInRole Under the Request Wrapper

With a Spring Security-integrated request:

```java
Principal principal = request.getUserPrincipal();
String name = (principal == null) ? null : principal.getName();
boolean permitted = request.isUserInRole("ADMIN");
```

Whether `isUserInRole("ADMIN")` succeeds depends on role mapping and `GrantedAuthority`. Do not assume container-supplied role names match Spring Security prefixes identically across deployments. In business code, complex checks should use method security or an authorization service with a consistent policy rather than checking `isUserInRole` in one controller while forgetting another API.

### 9.2. SecurityContextHolder Is Not an "Automatic Session"

`SecurityContextHolder` typically holds authentication info for the currently executing request. Persisting `SecurityContext` across requests also depends on `SecurityContextRepository`, session policy, and authentication filters. When building custom login or setting `Authentication` manually in Spring Security 6, understand when **saveContext** occurs. Integrated programmatic Servlet login must also test real persistence, as shown in section 8.

A stateless API using bearer tokens may have no session to invalidate; calling `request.logout()` in that case cannot turn a client's access token into an invalid token. Always distinguish **web session logout** from **token revocation**.

## 10. Design Mistakes and How to Handle Them

**Mistake 1 — Calling authenticate and still writing a response after a challenge.** After `request.authenticate(response) == false`, a redirect or 401 may already have been sent; writing JSON afterward causes double-commits or inconsistent responses. Check both the boolean and `isCommitted()` before writing further.

**Mistake 2 — Using authenticate to "check login" when you do not want a redirect.** If you only want to read status for UI rendering, use `getUserPrincipal()` or Spring Security's authentication state. `authenticate` actively triggers the authentication mechanism.

**Mistake 3 — Putting login in GET / query strings.** Passwords easily leak in logs, browser history, proxies, and analytics. Use a POST body over HTTPS, CSRF for browser sessions, brute-force limits, and never log credentials.

**Mistake 4 — Adding request.login when only OIDC is configured.** The API accepts username/password, but `AuthenticationManager`/container has no matching authentication mechanism. Use standard form login or OIDC redirects per contract instead of collecting IdP passwords yourself.

**Mistake 5 — Assuming login success in one request means the next request is logged in.** `SecurityContextRepository`, session policies, SaveContext, authentication strategies, and filter chains may differ. Test across two real HTTP requests, verifying session fixation and cookies.

**Mistake 6 — Calling request.logout and declaring full SSO logout.** Local sessions, IdP sessions, and refresh/access tokens are independent states. Implement RP-initiated logout/Single Logout, token revocation, or expiration by design.

**Mistake 7 — Allowing logout via GET for easy link clicking.** Logout mutates state and can be triggered unintentionally. Prefer POST with a valid CSRF token for web sessions.

**Mistake 8 — Skipping authorization checks after authenticate.** `authenticate` only verifies the caller; role and resource authorization must still be enforced separately.

**Mistake 9 — Using `web.ignoring()` on controllers that want Servlet API integration.** Requests may bypass Spring Security filters and remain unwrapped, leading to unexpected principal and logout behavior.

**Mistake 10 — Mixing multiple chains/filters/entry points.** One chain using form login for browsers and another using Basic or bearer tokens for APIs produce different challenges. Identify which chain handles each URL and test status/redirect/cookie behavior on that endpoint.

**Mistake 11 — Trusting the request wrapper as the sole boundary.** If a container realm, reverse proxy, or gateway authenticates requests, ensure direct requests cannot bypass identity enforcement and forwarded headers cannot be spoofed. Spring Security does not automatically verify arbitrary client-sent `X-User` headers.

**Mistake 12 — Equating CSRF 403 with "wrong password".** On POST login/logout, a missing CSRF token causes requests to be blocked **before the controller**. Inspect the right filter/event instead of disabling CSRF globally to hide the error.

## 11. Designing a Test Matrix for Real Applications

| Case | Expectation | Required Evidence |
|---|---|---|
| Anonymous GET public | 200 | Public resources remain accessible without a principal |
| Anonymous GET protected | 302 login or 401 per entry point | Protected data is not returned |
| request.authenticate when already logged in | `true` / handler continues | Valid principal; response is not re-challenged |
| request.authenticate when unauthenticated | `false` / mechanism-specific challenge | Business body is not written after entry point |
| request.login with correct password | Succeeds | Valid principal on current request **and subsequent request** when session-backed |
| request.login with wrong password | Does not create session | Generic error without leaking account details |
| POST login missing CSRF | Rejected at CSRF filter | Login handler does not process credentials |
| POST login with CSRF | Evaluated by authentication manager | Verify status and session/cookie |
| request.logout on current session | Clears context/session per contract | Subsequent request loses access; session invalidated if applicable |
| POST logout missing CSRF | Blocked | Session is not unexpectedly destroyed |
| Request with insufficient role | 403 | Authentication may succeed, yet authorization denies access |
| User with OIDC/SAML | Local logout does not log out IdP by default | Compare IdP session with app session |
| Stateless API with bearer tokens | Do not rely on session logout to revoke tokens | Tokens remain valid or are revoked per dedicated policy |
| Misconfigured container realm | No bypass allowed | Requests cannot spoof a principal via headers or alternate URLs |

For investigations, log **request ID, endpoint, auth mechanism, authentication outcome, error category, and timestamp**. Never log raw passwords, `Authorization` headers, session IDs, one-time tokens, or full exceptions containing sensitive data. Distinguish statuses emitted by Spring Security filters, the Servlet container, Spring MVC, and proxies.

## 12. Self-Check Questions

**Q1.** Why can `request.authenticate(response)` return `false` without throwing an exception?

**Answer:** The authentication mechanism initiated a challenge/redirect that has not yet completed. The controller must not assume the caller is logged in or write further to the response.

**Q2.** If `request.login("learner", "password")` succeeds, has MFA been performed?

**Answer:** No. It only authenticated against the configured provider/realm using the supplied credentials. MFA/step-up is a separate policy that must be enforced and verified independently.

**Q3.** Why does a user receive 403 on POST programmatic login while controller logs show nothing?

**Answer:** The Spring Security CSRF filter may reject a POST lacking a token **before it reaches the controller**. Obtain the proper token rather than disabling CSRF.

**Q4.** Why can't `request.logout()` sign out all OAuth2/OIDC sessions in other apps?

**Answer:** It operates on the authentication state managed by the current app's Servlet/container/Spring Security stack. IdP sessions, other applications, and active tokens are independent states requiring dedicated protocols or processes to terminate.

**Q5.** Can `request.login` be called in a controller that does not pass through the Spring Security filter chain?

**Answer:** The Servlet API still exists, but success then depends on the container/realm mechanism; there is no guarantee it updates `SecurityContextHolder`. Identify the request wrapper and security owner of the endpoint before designing around it.

**Q6.** When should you use `request.authenticate(response)` instead of simply checking `getUserPrincipal()`?

**Answer:** When the business flow genuinely wants to **trigger the authentication mechanism** if unauthenticated. If you only need to read login state without issuing a challenge, use getters or authentication state rather than a side-effecting method.

## 13. Checklist and Takeaways

- [ ] Know whether the Servlet container or Spring Security is handling `authenticate/login/logout` calls.
- [ ] Ensure endpoints traverse the intended `SecurityFilterChain`; `SecurityContextHolderAwareRequestFilter` is active when needed.
- [ ] With `authenticate`, never write to the response after the entry point handles a challenge; never treat `true` as sufficient business authorization.
- [ ] With `login`, accept credentials only in HTTPS POST bodies with CSRF for browser sessions, rate limiting, and generic error messages.
- [ ] Configure a proper user store/provider/realm so `login` truly authenticates; never fabricate unverified Authentications.
- [ ] Test security-context persistence, session fixation, logout handlers, and cookie lifecycle on the **subsequent request**.
- [ ] Invoke logout via POST with CSRF; distinguish local sessions, IdP sessions, remember-me tokens, and bearer tokens.
- [ ] Test low/high privileges, CSRF failures, wrong passwords, expired sessions, multiple chains, and reverse proxies.
- [ ] Never log credentials/tokens/session IDs; audit outcomes using a request ID.
- [ ] Never use Servlet APIs as a shortcut to bypass MFA, authorization, or filter chains.

**Summary:** `HttpServletRequest.authenticate(response)` **requests authentication or triggers a challenge**; `login(username,password)` **requests programmatic authentication with credentials**; `logout()` **requests clearing the current authentication state**. In Spring Security Servlet, these methods integrate via a request wrapper, yet correctness still depends on `AuthenticationManager`, entry points, `SecurityContextRepository`, sessions, logout handlers, and authorization rules. For ordinary browser login/logout, prefer standard `formLogin()` and `logout()` filters; use the Servlet API when specific integration needs arise and back it with end-to-end tests.