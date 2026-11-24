# formLogin, httpBasic, and logout in Authentication Flow Testing — Spring Security Servlet

> **Scope:** HTTP testing on **Spring Security 6.x / Servlet / Spring MVC**, using Spring Boot 3.x, Java 17+, JUnit 5, and `spring-security-test` with `MockMvc`. This lesson focuses on **real form login, HTTP Basic authentication, session persistence across HTTP requests, and logout**, as opposed to merely simulating a user via `@WithMockUser` or `user()`. The illustrative configuration uses a single security chain with both form login and HTTP Basic for easy comparison; production applications should choose and arrange authentication mechanisms according to their threat model.

## 1. Goal: Test the Authentication Flow, Not Just "Endpoint Returns 200"

Three common scenarios:

1. A user submits **POST /login** with `username` and `password`. Spring Security must verify the credentials, create an `Authentication`, persist the security context in the session as configured, and redirect properly.
2. A client sends `Authorization: Basic …` on an HTTP request. Spring Security must decode the Basic credentials, validate the username/password, and then enforce authorization; requests with invalid credentials must be rejected.
3. An authenticated user submits **POST /logout** properly (including CSRF when enabled). Spring Security must clear the server-side authentication state and apply the logout success behavior.

Weak tests often just write:

~~~java
mvc.perform(get("/web/me").with(user("alice")))
   .andExpect(status().isOk());
~~~

This is a **fragment** using the Spring Security test post-processor `user()`. It is valuable when testing **authorization** for an assumed authenticated user, yet **does not prove** that passwords are checked, HTTP Basic headers are processed, a login session is created, or logout invalidates the session.

To test the **authentication flow**, you need to invoke **the right endpoint/mechanism** through the test filter chain, then verify both the outcome and the state afterward.

### Lesson Success Criteria

- Know what request the `formLogin()` test helper sends to `UsernamePasswordAuthenticationFilter`.
- Know that the `httpBasic()` test post-processor actually builds a Basic header; distinguish it from `user()`.
- Verify login success/failure, requests without credentials, wrong credentials, session state, and authorization.
- Understand the difference between **real logout** and merely "clearing `SecurityContextHolder` in a test".
- Verify **CSRF** for login, logout, and state-changing business POSTs with a session.
- Never write tests hard-coded to the redirect URL, session behavior, or status code of a different configuration than the one actually running.

## 2. Three Mechanisms in the Servlet Filter Chain

~~~text
HTTP request
    |
    v
Servlet FilterChainProxy / SecurityFilterChain
    |
    +-- UsernamePasswordAuthenticationFilter
    |       POST /login
    |       username + password (+ CSRF if required)
    |       -> AuthenticationManager
    |       -> AuthenticationProvider / UserDetailsService
    |       -> success: SecurityContext + session/redirect
    |       -> failure: redirect or failure handler
    |
    +-- BasicAuthenticationFilter
    |       Authorization: Basic base64(username:password)
    |       -> AuthenticationManager
    |       -> valid: Authentication for the request
    |       -> invalid: usually 401 + WWW-Authenticate
    |
    +-- LogoutFilter
    |       default POST /logout when CSRF is enabled
    |       -> LogoutHandler(s), e.g. invalidation/session/context
    |       -> LogoutSuccessHandler / redirect
    |
    +-- AuthorizationFilter
            -> authorized: Controller
            -> missing Authentication: entry point / 401 or redirect
            -> missing authority: AccessDeniedHandler / usually 403
~~~

This is a conceptual diagram, **not the complete order of every filter**. In practice, `CsrfFilter`, `SecurityContextHolderFilter`/repository, `ExceptionTranslationFilter`, `RequestCacheAwareFilter`, and many other filters also participate.

**Key point:** `formLogin` and `httpBasic` are **two different authentication mechanisms**; `logout` mainly affects **state/session/cookies** and logout handlers, and cannot unconditionally prevent a valid Basic credential sent again by the client on the very next request.

### Quick Comparison

| Criterion | Form login | HTTP Basic | Logout |
| --- | --- | --- | --- |
| Client input | Username/password in form POST. | `Authorization: Basic …` header on each request. | Request to the logout endpoint, usually POST with CSRF token. |
| Spring Security component | `UsernamePasswordAuthenticationFilter`. | `BasicAuthenticationFilter`. | `LogoutFilter`. |
| Primary result | `SecurityContext`, typically a login session and redirect. | `Authentication` for the request. | Clears authentication/session and redirects/responds. |
| Client model | Browser/web application. | API client/tool, sometimes browser. | Browser/session-based logout. |
| Test helper | `formLogin()`. | `httpBasic("u","p")`. | `logout()` or POST with `csrf()`. |
| Verification technique | `authenticated()`, redirect, session, post-login request. | HTTP 200/401, principal, `WWW-Authenticate`. | Old session invalid, logout success, post-logout request. |

HTTP Basic only **Base64-encodes**, and does not securely encrypt passwords; use HTTPS for real credentials. Browsers may cache and resend Basic credentials on subsequent requests, so never conclude "once logged out, Basic will never re-authenticate".

## 3. What Does spring-security-test Provide?

The `spring-security-test` dependency brings these tools into MockMvc:

| API | Kind | Purpose |
| --- | --- | --- |
| `formLogin()` | `RequestBuilder` | Simulates a POST to the form login processing URL with username/password and matching CSRF. |
| `httpBasic("user","pass")` | `RequestPostProcessor` | Creates the appropriate Basic header for a request. |
| `logout()` | `RequestBuilder` | Creates a logout request using the helper's default convention and CSRF. |
| `csrf()` | `RequestPostProcessor` | Attaches a valid CSRF token when testing CSRF-protected endpoints. |
| `csrf().useInvalidToken()` | `RequestPostProcessor` | Tests an invalid token. |
| `authenticated()` | `ResultMatcher` | Checks authentication state in the MockMvc result. |
| `authenticated().withUsername("alice")` | `ResultMatcher` | Verifies the authenticated user has the expected username. |
| `unauthenticated()` | `ResultMatcher` | Verifies there is no authenticated user authentication. |
| `user("alice")` | `RequestPostProcessor` | Injects a test principal; **does not test credential validation**. |
| `@WithMockUser` | Test annotation | Places a mock `Authentication` into the test context; suitable for authorization tests. |

Common static imports:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
~~~

**Note:** `formLogin()` and `logout()` return **request builders**, whereas `httpBasic()` and `csrf()` are **post-processors** used with `.with(…)` on a `MockHttpServletRequestBuilder`:

~~~java
mvc.perform(formLogin().user("alice").password("demo-pass"));
mvc.perform(get("/api/me").with(httpBasic("alice", "demo-pass")));
mvc.perform(post("/web/action").with(csrf()));
mvc.perform(logout());
~~~

These are fragments inside a test class where `mvc` is initialized. Do not call `.with(httpBasic(...))` on the result of `formLogin()` if that builder API does not support `with`.

### Spring Security Filters Must Be Active in MockMvc

In Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {
    @Autowired MockMvc mvc;
}
~~~

This setup loads the Spring context and integrates standard security filters. For MockMvc built manually with `MockMvcBuilders.webAppContextSetup(context)`, call `.apply(springSecurity())` or wire `FilterChainProxy` properly.

**Do not use `@AutoConfigureMockMvc(addFilters = false)`** and then claim to verify login/CSRF/logout: with filters disabled, you may be testing a controller completely detached from the production security flow. Similarly, standalone MockMvc without a filter chain can let tests "pass" without actually running Spring Security.

## 4. A Complete Java 17+ Project to Run Tests

We build a minimal Spring Boot MVC application:

- `GET /public`: no login required.
- `GET /api/me`: displays the caller, used to test Basic.
- `GET /web/me`: displays the caller via session after form login.
- `POST /web/action`: a **simulated** state-changing endpoint used to demonstrate CSRF. It writes no data and transfers no real money.
- `POST /login`: handled by the Spring Security filter, no custom Controller handler written.
- `POST /logout`: handled by the Spring Security filter, no custom Controller handler written.

### Directory Structure

~~~text
security-http-tests/
  pom.xml
  src/
    main/
      java/com/example/securityhttptests/
        SecurityHttpTestsApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/com/example/securityhttptests/
        AuthenticationFlowTest.java
~~~

This lesson uses **Spring Boot 3.3.5** as the reference version with Java 17; this is a concrete version so the example is reproducible, **not a claim that it is the latest release**.

### 4.1. Maven pom.xml

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-http-tests</artifactId>
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
~~~

The Maven parent manages compatible library versions. The test framework uses JUnit Jupiter and Spring Test. No OAuth2/JWT libraries are needed here; `formLogin` and Basic use `UserDetailsService`/`PasswordEncoder`.

### 4.2. Main Application

**`src/main/java/com/example/securityhttptests/SecurityHttpTestsApplication.java`:**

~~~java
package com.example.securityhttptests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityHttpTestsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityHttpTestsApplication.class, args);
    }
}
~~~

### 4.3. Authentication and Endpoint Protection Configuration

**`src/main/java/com/example/securityhttptests/SecurityConfig.java`:**

~~~java
package com.example.securityhttptests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            // Do not disable CSRF: protects POST /login, /logout
            // and POST /web/action per the default configuration.
            .build();
    }
}
~~~

**Explanation:**

1. `formLogin(Customizer.withDefaults())` enables the default login page and default processing URL `POST /login`. Default form fields are `username` and `password`. Successful login normally triggers a **302 redirect** to the saved request or default target; failure usually redirects to `/login?error`.
2. `httpBasic(Customizer.withDefaults())` enables HTTP Basic credentials on requests; if invalid, it normally returns 401 and a Basic challenge. If no credentials are sent, the entry point may be a Basic challenge or a form login redirect **depending on request matchers/content negotiation**.
3. `logout(Customizer.withDefaults())` enables the logout endpoint and by default invalidates the session and clears the security context; when CSRF is enabled, the logout action defaults to `POST /logout`. A successful response normally redirects to `/login?logout`.
4. `requestMatchers("/public").permitAll()` is a URL policy, not a bypass of all filters. `anyRequest().authenticated()` requires authentication for the remaining endpoints.
5. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` creates password hashes compatible with password authentication. The hardcoded password `demo-pass` is **for this lesson only**; in production, never embed default account passwords in source code.
6. We **do not** use `SessionCreationPolicy.STATELESS` here: the test goal is to observe the form-login session. Setting stateless would break the session tests. HTTP Basic and form login are combined **solely for this demo**; production APIs and UIs should usually have separate chains/policies.
7. Do not write `.csrf(csrf -> csrf.disable())` just to make POST tests pass. When browsers and session cookies are involved, CSRF is part of the threat model that must be verified.

**Distinguish the components:** `UserDetailsService` looks up accounts, `PasswordEncoder` helps verify passwords through the provider; controllers do not verify passwords themselves. The `formLogin()` test helper sends the real request to the security filter rather than calling `SecurityContextHolder.setAuthentication(...)` directly.

### 4.4. Controller

**`src/main/java/com/example/securityhttptests/DemoController.java`:**

~~~java
package com.example.securityhttptests;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> basicIdentity(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/web/me")
    public Map<String, String> sessionIdentity(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @PostMapping("/web/action")
    public Map<String, String> fakeAction(Authentication auth) {
        // Simulated state-changing endpoint for testing CSRF.
        // No actual business side effects.
        return Map.of(
            "result", "accepted",
            "user", auth.getName()
        );
    }
}
~~~

Although `/api/me` and `/web/me` both return the same `user` field, **the authentication mechanism** differs: the first test sends a Basic header on the request, while the second reuses the session after form login.

Do not create `@PostMapping("/login")` or `@PostMapping("/logout")` in the Controller: under this configuration, those two URLs are intercepted and handled by Spring Security filters before MVC. Writing handlers at the same paths does not replace the authentication/logout chain.

## 5. Complete MockMvc Test Suite

**`src/test/java/com/example/securityhttptests/AuthenticationFlowTest.java`:**

~~~java
package com.example.securityhttptests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
    .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicPageWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void correctBasicCredentialsAuthenticateUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("alice"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void incorrectBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void formLoginSucceedsAndSessionAuthenticatesNextRequest()
            throws Exception {

        MockHttpSession session = loggedInSession();

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void incorrectFormLoginRedirectsToError() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void rawLoginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void sessionPostNeedsCsrfToken() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/web/action").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(post("/web/action")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("accepted"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/web/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void postLogoutWithCsrfInvalidatesFormSession()
            throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());
    }

    private MockHttpSession loggedInSession() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                .user("alice")
                .password("demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }
}
~~~

**Why does this example test the real flow?**

- `httpBasic("alice", "demo-pass")` creates a Basic header so `BasicAuthenticationFilter` validates real credentials via the configured provider.
- `formLogin().user(...).password(...)` sends a login request and **includes a valid CSRF token via the test helper**. Thus it tests **username/password authentication**, rather than merely inserting a fake user.
- `loggedInSession()` captures the session from the successful form-login request and passes `.session(session)` on the next request. That tests **security context persistence across requests**, not just the "authenticated" status within the login POST itself.
- `post("/login").param(...)` has **no** CSRF token and gets 403 from `CsrfFilter`, showing how a raw POST differs from the `formLogin()` helper.
- `post("/web/action").session(session)` must be rejected even though the user is logged in, because CSRF is missing. Adding `.with(csrf())` lets the POST reach the controller.
- `post("/logout").session(session).with(csrf())` actually uses the **authenticated session** and verifies it is invalidated. The `/login?logout` redirect matches the demo project's default logout configuration.

`MockHttpSession.isInvalid()` works with `org.springframework.mock.web.MockHttpSession` in the corresponding Spring Test versions. Do not reuse an **already invalidated session** for a subsequent request: the servlet session is no longer valid and `MockHttpSession` may throw an exception if accessed after invalidation. To verify post-logout access with a new HTTP request, create a fresh unauthenticated session/client state and verify the protected endpoint still blocks it.

### Running the Test Suite

In the directory containing `pom.xml`:

~~~bash
mvn test
~~~

The expectation is that all authentication, Basic, CSRF, and logout tests pass when run with the project's Spring Boot 3.x/Spring Security 6.x setup. **There is no fixed Maven stdout** because logs, dependency caches, Java versions, and test reporters vary across machines. If a test fails, read the **specific assertion** and security filter configuration rather than changing the policy to `permitAll`/`csrf.disable()` to "turn it green".

To run the application:

~~~bash
mvn spring-boot:run
~~~

HTTP Basic locally:

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/me
~~~

Expected JSON body:

~~~json
{"user":"alice"}
~~~

Use HTTPS when testing real credentials; `localhost` HTTP URLs are strictly for demo purposes. Never place production passwords in shell history, source code, or public test docs.

## 6. Deep Dive into formLogin(): What Does It Verify?

### 6.1. Request and State Flow

~~~text
MockMvc
  |
  | formLogin().user("alice").password("demo-pass")
  | POST /login, username, password, CSRF
  v
CsrfFilter (valid)
  |
  v
UsernamePasswordAuthenticationFilter
  |
  v
AuthenticationManager
  |
  v
Provider checks PasswordEncoder and UserDetailsService
  |
  +-- Valid   -> Authentication succeeds
  |           -> SecurityContext saved per session/repository
  |           -> success handler, usually 302 redirect
  |
  +-- Invalid -> authentication failure
              -> failure handler, usually 302 /login?error
~~~

`authenticated().withUsername("alice")` placed after the login request states that **the request outcome is authenticated per the test matcher**. It does not automatically test session state on the next request, which is why we extract `MockHttpSession` and perform `GET /web/me` in a separate step.

### 6.2. Login Success Does Not Always Redirect to the Same URL

When a user visits a protected URL before logging in, Spring Security may save a `SavedRequest` via `RequestCache`. Successful login can redirect back to that original URL. If the user logs in directly, it may redirect to the default target (often `/`).

Therefore, in a **general login success test**, assert `status().is3xxRedirection()` and `authenticated()` first; only assert an exact redirect URL when you **explicitly configured a success URL/handler** or are specifically testing a saved request.

**Example you should not hard-code across every app:** `redirectedUrl("/")`. If the project sets `defaultSuccessUrl("/dashboard", true)`, the expected URL is `/dashboard`; if using a saved request, the URL can be whichever page was requested first.

### 6.3. Wrong-Password Tests Must Pass Through the Real Provider

~~~java
mvc.perform(formLogin()
        .user("alice")
        .password("wrong-password"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?error"))
    .andExpect(unauthenticated());
~~~

In the demo, Spring Security uses `UserDetailsService` and `PasswordEncoder`, so this test catches credential errors. If you only used `@WithMockUser("alice")`, the test **would not prove** that `"wrong-password"` is rejected.

A login failure handler may be customized by a project to return JSON 401 instead of redirecting. In that case, tests must assert against the **real contract** rather than the default form-login behavior.

### 6.4. Custom Login URL and Parameter Names

If production configures:

~~~java
.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/auth/signin")
    .usernameParameter("email")
    .passwordParameter("secret")
    .permitAll())
~~~

then login POSTs must go to `/auth/signin` with fields `email` and `secret`. You can test with a raw POST:

~~~java
mvc.perform(post("/auth/signin")
        .param("email", "alice@example.test")
        .param("secret", "example-password")
        .with(csrf()));
~~~

This is an illustrative fragment; it is **not directly compatible** with the demo project's `alice`/`demo-pass` account unless `UserDetailsService` and login config are updated. The goal is to grasp the **processing URL and parameter contract**, rather than repeating the default login test against a different URL.

**Distinguish:**
- `loginPage("/signin")`: GET URL rendering the login form (needs a controller/view if customized).
- `loginProcessingUrl("/auth/signin")`: POST URL intercepted by the filter to authenticate.
- `usernameParameter` and `passwordParameter`: form field names read by the filter.
- `defaultSuccessUrl` and `failureUrl`: control the response/redirect after authentication.

If you customize the login URL and forget `permitAll`/the proper authorization rule, unauthenticated users can be blocked right at the login path or trapped in a redirect loop.

## 7. HTTP Basic: What Must Be Asserted?

### 7.1. How Is the Basic Header Built?

Standard HTTP Basic sends:

~~~http
Authorization: Basic <base64(username:password)>
~~~

`httpBasic("alice", "demo-pass")` builds that header for the test request:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "demo-pass")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.user").value("alice"));
~~~

The framework checks the credentials through the configured `BasicAuthenticationFilter`/provider. Never concatenate `"Basic alice:demo-pass"` manually because that is **not valid Base64**. Also never treat Basic encoding as network security; HTTPS is mandatory.

### 7.2. Credential Failure Is Usually 401

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "wrong-password")))
    .andExpect(status().isUnauthorized());
~~~

In the default Basic mechanism, a failed authentication response typically includes `WWW-Authenticate: Basic realm="Realm"` or the app's configured realm, though **do not hard-code the realm string** unless there is an explicit contract.

When no `Authorization` header is present, an app enabling **both form login and Basic** may choose **302 redirect** or **401 Basic challenge** based on content negotiation/request matchers. Therefore, asserting "GET `/api/me` without header is always 401" may not hold for every chain. In the example, testing **invalid Basic credentials** is more deterministic for verifying Basic failure, while entry-point selection for missing credentials should be tested per `Accept` header and the real security config.

### 7.3. Authenticated Basic Does Not Automatically Mean Stateless

Because the demo uses one security chain with both form login and Basic, a session/repository may still participate in the request. HTTP Basic itself does not require storing a session, yet the **`SecurityFilterChain` configuration** determines whether the security context is persisted, sessions are created, or request caching runs.

In production, APIs meant to be stateless typically use a separate `/api/**` chain with `SessionCreationPolicy.STATELESS`, dedicated CSRF/threat-model policies, and an entry point returning 401 JSON/Basic challenges; browser UIs use a separate chain with sessions/form login. Do not set `STATELESS` globally across the whole app if you want to test login sessions.

### 7.4. Brute-Force Protection and Credential Leakage

Right-password/wrong-password tests are the baseline. Production also needs rate limiting, account lockout/anti-credential-stuffing policies, login-failure auditing, HTTPS, never logging `Authorization` headers, and never storing real passwords in shared public test fixtures.

A new Basic request with valid credentials can still authenticate even after a **separate form-login session** logged out. Because Basic credentials are re-sent by the client, **logout cannot erase the password held by the client/browser**.

## 8. logout(): What to Check Beyond the Redirect?

### 8.1. Default Logout Flow When CSRF Is Enabled

~~~text
Authenticated session
        |
        | POST /logout + valid CSRF token
        v
LogoutFilter
        |
        +-- LogoutHandler(s):
        |    clear SecurityContext
        |    invalidate HttpSession (per configuration)
        |    remove/adjust related state
        |
        v
LogoutSuccessHandler
        |
        v
302 /login?logout (default demo)
~~~

`logout()` from `SecurityMockMvcRequestBuilders` is a helper for building a logout request, similar to the form login helper. However, when you want to prove **a specific session** was cleared, use an explicit POST with `session(session)` and `csrf()` as in section 5; the simple helper works when testing the default logout endpoint/status:

~~~java
mvc.perform(logout())
    .andExpect(unauthenticated());
~~~

This is a fragment requiring the appropriate static imports. This test **is not enough to prove** that a session created by a real login was invalidated. Combining it with a session-driven test is necessary.

### 8.2. Why Must POST /logout Missing CSRF Be Blocked?

CSRF protects a browser/session cookie from malicious websites triggering unintended logouts or actions via forged requests. In the demo's **CSRF-enabled** configuration:

~~~java
mvc.perform(post("/logout").session(session))
    .andExpect(status().isForbidden());
~~~

Here `session` is a variable from a logged-in test, not a standalone snippet. After the rejected request, the session must remain valid:

~~~java
assertFalse(session.isInvalid());
~~~

When a valid CSRF token is added:

~~~java
mvc.perform(post("/logout")
        .session(session)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());
~~~

the session must be invalidated per the demo config:

~~~java
assertTrue(session.isInvalid());
~~~

If the application customizes logout success to return 204 instead of 302, assert the status matching your contract. If the app disables `invalidateHttpSession` or uses a custom logout handler, never copy `isInvalid` assertions blindly; verify the exact state required by your security policy.

### 8.3. Does GET /logout "Log Out"?

In Spring Security Servlet with CSRF enabled, **GET /logout** usually displays a framework-generated logout confirmation page, whereas the actual logout action requires a POST with a CSRF token. Thus this test:

~~~java
mvc.perform(get("/logout"));
~~~

does not prove the user logged out. If a system is customized so `GET /logout` signs out directly, evaluate the CSRF/side-effect risk because GET should not perform state-changing actions. Do not switch POST to GET merely for browser navigation convenience.

### 8.4. Session Invalidation Is Different from Revoking All Tokens

A Servlet app's default logout typically invalidates the session and clears the security context; it **does not automatically**:
- revoke an OAuth2 Resource Server JWT access token;
- revoke tokens stored on other devices;
- delete custom cookies on other domains;
- stop clients from re-sending Basic credentials;
- clear distributed caches/remember-me tokens unless corresponding handlers are configured.

If the app has remember-me, OIDC logout, SSO, a session registry, or custom cookies, test those logout handlers and client/remote states explicitly. Logging out of App A does not automatically close the IdP session for the whole SSO realm.

## 9. CSRF: A Protection Layer You Cannot Ignore When Testing Login/Logout

In the demo, CSRF is **enabled by default**. Safe GET requests usually do not need a CSRF token; POST/PUT/PATCH/DELETE requests usually require a valid token when covered by CSRF protection.

| HTTP request | Authenticated? | CSRF token? | Expected in demo |
| --- | --- | --- | --- |
| GET /public | No | No | 200 |
| POST /login valid credentials | Not yet | No | 403 |
| POST /login valid credentials via `formLogin()` | Not yet | Helper adds token | 302 login success |
| GET /web/me with login session | Yes | No | 200 |
| POST /web/action with session | Yes | No | 403 |
| POST /web/action with session | Yes | Yes, valid | 200 |
| POST /logout with session | Yes | No | 403, session intact |
| POST /logout with session | Yes | Yes, valid | 302, session invalid |
| GET /api/me with valid Basic | Via Basic | No | 200 |
| GET /api/me with invalid Basic | Failed | No | 401 |

Do not infer from "API uses Basic" that every POST is exempt from CSRF. Browsers can automatically send Basic credentials/cookies depending on context; analyze whether credentials are **automatically attached** on cross-origin requests. When building an API chain that only accepts Bearer tokens explicitly placed in the Authorization header by the client, the CSRF threat model can differ. Disabling CSRF is a **policy decision**, not a trick to make tests pass.

### Testing an Invalid CSRF Token

An additional negative test:

~~~java
mvc.perform(post("/web/action")
        .session(session)
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

This is a fragment inside a test with an already-logged-in `session`. It distinguishes "a token field/header is present" from "the token matches the repository/handler". When using a custom `CsrfTokenRepository` or XOR token request handler, integrate it properly in the security filter chain so real verification is not bypassed.

## 10. Test Matchers: authenticated(), unauthenticated(), and Different Status Codes

`authenticated()` is not the same as `status().isOk()`:
- Authentication can succeed while the response is a 302 post-login redirect.
- An endpoint can return 200 due to `permitAll`, even when the caller is unauthenticated.
- Valid Basic credentials for a user lacking a role can return 403 even though the user is `authenticated`.
- A request with a session and valid CSRF can still return 403 due to missing authority or business policy.

Therefore each test should check **both dimensions**:
1. **Authentication state**: is the right user/authority authenticated?
2. **HTTP behavior**: status, redirect, headers, JSON, session, CSRF, and permissions.

Example:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("alice", "demo-pass")))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("alice"))
    .andExpect(jsonPath("$.user").value("alice"));
~~~

When testing a successful login request, a 302 response is not a sign of "login failed". Conversely, a 200 response on a public endpoint **does not prove** credentials were ever checked.

### Do Not Read SecurityContext at the Wrong Time

In Servlet, the security context may be cleared at the end of a request to prevent ThreadLocal leakage into another request. If a test outside the request calls:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

and gets null, that does not necessarily mean login inside the request failed. Verify via the `authenticated()` matcher on the request result, capture the login session, or issue a follow-up request with that same session. Never use a static `SecurityContext` as shared "login state" across multiple test methods.

## 11. Sessions, Cookies, and Verifying State Across Multiple HTTP Requests

MockMvc is not a real browser with an automatic cookie jar across every call. When you need to simulate a user continuing requests after login, an explicit way is:

~~~java
MvcResult login = mvc.perform(formLogin()
        .user("alice")
        .password("demo-pass"))
    .andExpect(authenticated())
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

assertNotNull(session);

mvc.perform(get("/web/me").session(session))
    .andExpect(status().isOk());
~~~

This is a fragment inside a test that already has `mvc` and imports. Passing the **exact session** matters: the test proves the security context was saved and restored by the Spring Security repository across requests.

### Session Fixation and Session ID

The framework may rotate the session ID after login to mitigate session fixation. Do not capture a pre-login session ID and assert it always equals the post-login ID. If policy requires session fixation protection, test it explicitly via appropriate MockMvc/session semantics rather than inferring it from "formLogin status 302".

### Distinguishing Authentication from Session

A valid Basic request may authenticate **only for that request**, without necessarily creating/maintaining a session. A form login request usually creates a session so the browser can use a session cookie. In the single-chain demo, both share one security config; do not conclude that all Basic requests are stateless or all form logins always use sessions in every configuration.

### Logout and Stale Browser Cookies

Once the server invalidates a session, a browser might still send an old session ID cookie. An old cookie **does not automatically resurrect an invalidated session**. However, if the client simultaneously sends a valid Basic header or holds an active OIDC session cookie at the IdP, the system can re-authenticate via another mechanism. Thus logout tests should state clearly: **which mechanism logs out, which state is cleared, and which credentials remain**.

## 12. Multiple SecurityFilterChains: Avoiding Testing the Wrong Chain

Production commonly separates UI and API:

~~~text
GET/POST /web/**  -> UI security chain:
   form login, session, CSRF, logout, redirects

/api/**           -> API security chain:
   HTTP Basic or Bearer, separate status/CSRF/session policies

other paths       -> fallback chain:
   deny/allow per explicit policy
~~~

When declaring multiple `SecurityFilterChain` beans using `@Order` and `securityMatcher`, ensure:

- `POST /login` actually matches the chain containing `formLogin`.
- `POST /logout` matches the chain containing `logout`.
- API challenge/entry points are not replaced by UI form-login redirects.
- No sensitive path falls outside every chain or gets matched by an overly broad matcher.
- Session fixation, CSRF, and request cache are configured appropriately per chain.
- Tests invoke the real login/logout URLs and also make post-authentication requests on the **chain they protect**.

**A classic bug:** the UI chain sets `securityMatcher("/web/**")`, yet the login processing URL remains `/login` **outside** that matcher, causing login requests to hit a different chain or miss the form filter altogether. You can set `loginProcessingUrl("/web/login")` and a logout URL inside the UI chain or widen the matcher properly, then update tests.

Do not copy a default `formLogin()` test fragment into a configuration using `loginProcessingUrl("/web/login")` without updating the URL. Tests must verify the **active contract**, not the helper's name.

## 13. A Practical Authentication Testing Matrix

Organize tests into distinct groups rather than a single happy path.

| Group | Key scenario | Minimum observation |
| --- | --- | --- |
| Public | GET /public without login | 200, expected content |
| Form login success | Valid username/password, valid CSRF | Authenticated properly, redirect, session saved |
| Form login failure | Wrong password, unknown user | Unauthenticated, matching failure handler |
| Form login CSRF | POST /login missing/invalid CSRF | Rejected, no authenticated session created |
| Basic success | Valid Authorization Basic | Authenticated right user, controller gets right principal |
| Basic failure | Invalid Authorization Basic | 401/matching challenge |
| Missing credentials | GET protected without credentials | Login redirect or 401 per chain/Accept |
| Session persistence | After login, GET protected with same session | Succeeds, right user |
| Authorization | Authenticated but lacking role | 403, no data leak |
| Business CSRF | POST with session yet missing CSRF | 403; valid CSRF reaches controller |
| Logout protection | POST /logout missing CSRF | Rejected, session not invalidated |
| Logout success | POST /logout valid CSRF | Handler runs; session invalid, expected redirect/response |
| Multi-chain | UI vs API vs fallback | Right security chain, status/redirect/CSRF per policy |
| SSO/remember-me | App logout and refresh/browser state | Session and tokens cleared/retained per actual policy |

For "missing credentials" cases, avoid asserting a single rigid status if the app enables both Basic and form login using content negotiation. **Configure an explicit entry point** if the public API contract mandates a specific status, and test that.

### Add Post-Authentication Authorization Tests

`formLogin`/`httpBasic` only verifies **who** logged in, not that the user is allowed everywhere. If a route requires `hasRole("ADMIN")` and `alice` only has `ROLE_USER`, the request must get 403. Writing "correct credentials but insufficient authority" tests prevents accidentally conflating authentication with authorization.

## 14. Debugging at the Right Layer When Tests Fail

### Case A: formLogin Returns 403

Check `CsrfFilter`, whether the login URL matches the security chain, whether `formLogin()` uses the right processing URL/parameters, and whether a custom CSRF repository accepts the token from the helper. When using a raw POST, add `.with(csrf())` if CSRF is enabled.

**Do not "fix" it with `csrf.disable()` if the app uses browser sessions.**

### Case B: formLogin Returns 302, Yet GET /web/me Still Redirects to Login

Usually because the test did not carry the **session** after login, the session is not saved/restored by the repository, `STATELESS` is configured, or the follow-up request hit a different chain. Check `getSession(false)`, `MockHttpSession`, `.session(session)`, and `SecurityContextRepository`.

### Case C: Valid Basic Redirects to Login Instead of Returning JSON

Check whether `BasicAuthenticationFilter` is in the matching chain, whether the path matches the chain, whether credentials are right, and whether another policy blocked the endpoint. If the request **has no** Basic header, the entry point may redirect per form login; if the Basic header is invalid, it typically returns 401.

### Case D: Logout Test Passes Yet User Is Still "Logged In"

Check whether the test used a **real pre-login session** or just mock authentication; verify the logout URL, method, CSRF, handlers, and which server-side state was cleared. If the client/browser keeps sending Basic credentials or has remember-me/SSO sessions, post-logout requests can re-authenticate. **Session logout does not delete client-side passwords.**

### Case E: @WithMockUser Passes While formLogin Fails

There is no contradiction. `@WithMockUser` places a fake user in the security context; it bypasses the username/password provider. Form login exercises **`UserDetailsService`, `PasswordEncoder`, and the login filter**. Check that the account exists, the hash format matches, and the authentication manager is wired.

### Case F: Logout via GET Does Nothing

When CSRF is enabled, `GET /logout` is by default a confirmation page and `POST` executes logout. Use `post("/logout").with(csrf())` with an authenticated session when testing the logout action. Do not switch to GET arbitrarily.

### Case G: "Unauthenticated" Test Gets 302 When Expecting 401

The app has form login enabled, which may redirect to the login page when `Accept: text/html`. API clients usually expect 401. If you need a consistent JSON API, design a dedicated chain/entry point for the API and test it accordingly. Do not treat every 302 response as a bug.

### Case H: POST /web/action Returns 403 Even After Successful Login

First separate CSRF 403 from authorization 403. In the demo, `CsrfFilter` blocks a POST missing a CSRF token **before** the controller runs. Add `.with(csrf())` to test the flow past CSRF, and only then evaluate authority/business rules.

## 15. Misconceptions to Avoid

**"formLogin() is the same as @WithMockUser."** False. `formLogin()` submits form credentials through the Spring Security authentication flow; `@WithMockUser` injects a fake `Authentication` for policy/controller tests.

**"httpBasic() just puts a username in the security context."** False. `httpBasic()` constructs an HTTP Basic header; the provider still checks username/password. `user()` is the helper that sets a fake principal on the request.

**"Successful login must return status 200."** False. Default form login usually redirects 302; tests must check `authenticated()`, redirect, and session state.

**"One login test returning 302 is enough to prove the session."** False. You need a subsequent request using the same `MockHttpSession` to prove the security context persisted.

**"Logout deletes all Basic/OAuth2 credentials too."** False. It clears state per logout handlers; credentials re-sent by the client or still-valid remote IdP tokens require separate policies.

**"Logout works via GET by default."** Incorrect when CSRF is enabled; `GET /logout` is typically only a confirmation page, while `POST` triggers logout.

**"Disabling CSRF is a good fix when login/logout tests return 403."** False for apps using browser/sessions. Tests must send a valid token, or the architecture must have a clear rationale for omitting CSRF.

**"HTTP Basic is secure because it uses Base64."** False. Base64 is not encryption; use TLS/HTTPS and never log credentials.

**"Authenticated means authorized."** False. A logged-in user can still get 403 from roles, permissions, CSRF, or business policies.

**"Form login and HTTP Basic always return the same error style."** False. Default form login tends to redirect; Basic usually returns 401/challenge, depending on entry point and request.

**"Tests using @AutoConfigureMockMvc(addFilters=false) still authenticate for real."** False. When security filters are bypassed, tests do not go through the production login/basic/logout/CSRF chain.

## 16. Practice Exercises

### Exercise 1 — Successful Login Followed by Access

Write a `formLogin().user("alice").password("demo-pass")` test and assert `authenticated()`. Capture `MockHttpSession` and perform `GET /web/me` with that session. **Expected result:** 200 response containing `"user":"alice"`.

### Exercise 2 — Wrong Password Across Both Mechanisms

Try `formLogin()` with a wrong password and `GET /api/me` with `httpBasic("alice","wrong-password")`. **Expected result:** form failure typically redirects to `/login?error`; Basic failure typically returns 401; neither can access protected endpoints as `alice`.

### Exercise 3 — Comparing Raw POST and the Helper

Send a raw `POST /login` with valid form fields but without CSRF. Then use `formLogin()`. **Expected result:** the raw request gets 403; the helper succeeds under the demo configuration. Explain the difference in terms of the CSRF token.

### Exercise 4 — Real Logout with Session

Log in and capture the session; `POST /logout` without CSRF and assert it is not invalid yet; then `POST` with CSRF and assert `session.isInvalid()`. **Expected result:** the first request gets 403, the second redirects on logout success and invalidates the session.

### Exercise 5 — Adding ADMIN Authorization

Add `/admin` restricted to `hasRole("ADMIN")`, then test Basic as `alice` who has `ROLE_USER`. **Expected result:** user is authenticated properly yet receives HTTP 403. Explain the difference between authentication and authorization in words.

### Exercise 6 — Separate API and UI Chains

Create an `/api/**` chain with Basic and a `/web/**` chain with form login, ensuring login/logout URLs belong to the UI chain. Write tests where Basic wrong password returns 401 and unauthenticated browser GET on UI redirects to the login page. **Expected result:** no endpoint or login handler falls outside all chains; CSRF/session policies are clear.

### Exercise 7 — Custom Form Login Parameters

Change the processing URL to `/auth/signin` and the username field to `email`. Write a raw POST test with the right URL and `.with(csrf())`, plus a negative test posting to the wrong `/login` URL. **Expected result:** only the configured URL and fields trigger successful login.

### Exercise 8 — Never Reuse a Session After Logout

Log in, log out, and verify the session is invalid. Attempt to access a protected endpoint using **a new request with no valid credentials/session**. **Expected result:** the request does not reach the controller and receives a redirect/401 per the entry point. Do not try to reuse an invalidated `MockHttpSession` because it may throw an exception and does not reflect a real HTTP client.

## 17. Checklist Before Accepting an Authentication Flow Test Suite

- [ ] Tests enable the real Spring Security filter chain in MockMvc.
- [ ] Form login tests cover **both valid and wrong passwords** through the real processing URL.
- [ ] Basic tests cover **both valid and wrong credentials** via the Authorization header.
- [ ] Unauthenticated protected requests are tested against the exact entry point contract.
- [ ] **Session persistence** after form login is tested with a follow-up request.
- [ ] CSRF is tested for raw login POST, state-changing endpoints, and logout.
- [ ] Logout is tested using **the actual session created by login** and invalidation is verified.
- [ ] Authorization is tested when a user is authenticated yet lacks required permissions.
- [ ] With custom login/logout paths, all tests are updated to match the real URLs/parameters.
- [ ] With multiple security chains, tests verify requests hit the intended chain.
- [ ] `@WithMockUser`/`user()` are never used as evidence of password verification.
- [ ] Filters/CSRF are never disabled just to "make tests turn green".
- [ ] Real passwords/tokens are never placed in test fixtures or logs.
- [ ] HTTP Basic logout is never misrepresented as revoking client-held passwords.
- [ ] All 200/302/401/403 expectations are based on the running configuration, not copied blindly.

**Conclusion:** In Spring Security Servlet, `formLogin()` tests **form POST authentication**, `httpBasic()` tests **Basic header credentials**, and `logout()`/`POST /logout` tests **tearing down login state**. A quality test suite must prove **credentials are validated properly, the session carries into the next request, CSRF is enforced, and logout invalidates the session per policy**, while testing authorization separately. The `authenticated()` matcher is very helpful, yet does not replace checking HTTP status, redirects, sessions, and protected endpoints.