# AbstractAuthenticationProcessingFilter and Pre/Post-Authentication Steps in Spring Security Servlet

In a Spring MVC application running on the Servlet stack, when a user submits a username and password, authentication is more than comparing two strings. Spring Security must recognize the login request, construct an authentication request, select an `AuthenticationProvider`, establish `SecurityContext`, handle the session, and decide the response on success or failure.

`AbstractAuthenticationProcessingFilter` is the base class providing the **orchestration framework** for Servlet filters that actively perform authentication at a designated endpoint. Its most common implementation is `UsernamePasswordAuthenticationFilter` for form login. Understanding this framework helps explain why a login request is rejected by CSRF, why login succeeds yet the next request becomes anonymous, or why a wrong password returns a redirect instead of HTTP 401.

**Scope:** Spring Security **Servlet** (Spring MVC, `HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest`), focusing on common mechanisms in Spring Security 6.x. Examples use Spring Boot 3.3.5 and Java 17+ as a learning baseline, without claiming this is the newest release or still supported at reading time. Spring WebFlux has its own reactive components and does not use this class inside `SecurityWebFilterChain`.

## 1. Position of AbstractAuthenticationProcessingFilter in the Filter Chain

```text
HTTP client / browser
       |
Servlet container
       |
DelegatingFilterProxy -> FilterChainProxy
       |
SecurityFilterChain matching the request
       |
(other security filters before the authentication filter)
       |
UsernamePasswordAuthenticationFilter
   extends AbstractAuthenticationProcessingFilter
       |
       +-- requiresAuthentication(request, response)?
       |     |
       |     +-- NO  -> filterChain.doFilter(...)
       |     |
       |     +-- YES -> attemptAuthentication(...)
       |                    |
       |              AuthenticationManager
       |                    |
       |              AuthenticationProvider
       |                    |
       |           Authentication / null / exception
       |
       +-- success -> session strategy -> successfulAuthentication(...)
       |
       +-- failure -> unsuccessfulAuthentication(...)
       |
       +-- null result -> ends branch awaiting authentication completion
       |
       +-- SuccessHandler / FailureHandler decides the response
```

The diagram is a logical model; the **exact number of filters and order** depend on configuration, authentication type, and version. When `requiresAuthentication` does not match, the filter simply forwards the request; other filters can still handle authentication or authorization. Conversely, when a request actually performs login, a success/failure handler typically produces a redirect or response, so that request does not necessarily reach an application controller.

For example, with default `formLogin()`:

- `GET /login` typically renders the framework-generated or custom login page. It is not the filter's username/password verification request.
- `POST /login` with form fields `username` and `password` is the default authentication processing endpoint; `UsernamePasswordAuthenticationFilter`'s matcher targets this request.
- `GET /profile` is not a login processing endpoint. The login filter forwards the request; authentication can be loaded from the session and authorization decides access.

**`permitAll()` does not disable the authentication filter.** It allows the request at the authorization step, while CSRF, authentication, session, and other filters still run as configured.

## 2. Contract of the Base Class

The base class handles three outcomes from the abstract method:

```java
public abstract Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response)
        throws AuthenticationException, IOException, ServletException;
```

This is an **API signature for explanation**, not a standalone runnable Java program. Subclasses must implement how to read request data, build an **untrusted** authentication request, and ask `AuthenticationManager` to verify it.

| Outcome from `attemptAuthentication` | Meaning | Next Branch |
|---|---|---|
| Returns a successfully authenticated `Authentication` | Manager/provider verified proof using the chosen mechanism | Run `SessionAuthenticationStrategy`, then call `successfulAuthentication` |
| Returns `null` | Authentication is not yet complete in the current request | Filter stops this request branch; does not automatically call success/failure handlers |
| Throws `AuthenticationException` | Authentication request failed or was rejected | Call `unsuccessfulAuthentication` and the failure handler |

`null` **does not mean wrong password**. It can represent an incomplete multi-step protocol where the subclass manages the response and needed state itself. By contrast, bad credentials normally produce a `BadCredentialsException` (an `AuthenticationException`).

### What Does UsernamePasswordAuthenticationFilter Do?

The form login implementation typically reads the `username` and `password` request parameters, builds an unauthenticated `UsernamePasswordAuthenticationToken`, and calls `AuthenticationManager.authenticate(...)`. This filter **does not decide** whether the password is valid on its own.

A typical authentication flow:

```text
POST /login
    |
UsernamePasswordAuthenticationFilter.attemptAuthentication(...)
    |
UsernamePasswordAuthenticationToken (untrusted)
    |
AuthenticationManager.authenticate(...)
    |
ProviderManager
    |
Provider supporting username/password
    +-- UserDetailsService reads account info
    +-- PasswordEncoder checks encoded password
    +-- account status rules (locked, disabled, expired ...)
    |
Authenticated Authentication or AuthenticationException
```

Never create a `UsernamePasswordAuthenticationToken` with authorities attached and put it into `SecurityContextHolder` directly from a client-supplied username. Factory methods such as `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` explicitly convey that initial input is untrusted. An authenticated `Authentication` object must come from a trusted manager/provider.

A provider may serve a mechanism other than form login, and a manager may coordinate multiple providers. The existence of `UserDetailsService` does not mean every request, including JWT Bearer or OIDC callbacks, is verified by form password.

## 3. Before Attempting Authentication: RequestMatcher, HTTP Method, CSRF

`requiresAuthentication(request, response)` relies on the filter's `RequestMatcher`. The matcher must match the expected HTTP path and method accurately.

With default form login, the authentication processing request is typically `POST /login`. You can change the URL:

```java
http.formLogin(form -> form
    .loginProcessingUrl("/signin")
    .permitAll());
```

This is a **code snippet inside an `HttpSecurity` configuration**. When changing the login processing URL, the client must also POST to the new URL, and the GET form page must be configured/verified accordingly. `loginPage` and `loginProcessingUrl` are not the same concept.

Before the login filter checks passwords, the request may already be blocked by another component:

1. **`CsrfFilter`** validates the CSRF token on POST requests in session/cookie-based web apps. A missing token can trigger HTTP 403 **before `attemptAuthentication` runs**.
2. **Servlet firewall/matcher** ensures normalized path matching or rejects malformed requests.
3. **Other security filters** handle headers, session, CORS, or other authentication mechanisms depending on filter order.
4. **`SecurityFilterChain` selection** determines whether the request even reaches the login filter. An overly narrow `securityMatcher` or a wrong `WebSecurityCustomizer.ignoring` rule can cause POST login to bypass the intended chain.

Therefore, when POST login returns 403, **do not assume the password was checked**. Inspect the CSRF token and chain matching before investigating the provider.

## 4. After Successful Authentication: Order Matters

In Spring Security 6's `AbstractAuthenticationProcessingFilter`, once `attemptAuthentication` returns a valid result, the core flow comprises:

1. **`SessionAuthenticationStrategy.onAuthentication(...)`**: applies session-related policies if configured, such as changing the session ID against session fixation, enforcing concurrent session limits, or other session rules. If this strategy throws an authentication exception, the flow can divert to the failure branch.
2. **`successfulAuthentication(...)`**: creates a new `SecurityContext`, sets the authenticated `Authentication` on it, sets it in `SecurityContextHolder`, and saves it via `SecurityContextRepository` as configured on the filter.
3. **Remember-me and events:** if configured, notifies `RememberMeServices.loginSuccess(...)`; may publish `InteractiveAuthenticationSuccessEvent`.
4. **`AuthenticationSuccessHandler.onAuthenticationSuccess(...)`**: sends the appropriate response, typically a redirect after form login or a custom response for the client.

```text
Authentication result
       |
SessionAuthenticationStrategy.onAuthentication(...)
       |
successfulAuthentication(...)
       |
SecurityContextHolder <- SecurityContext(Authentication)
       |
SecurityContextRepository.saveContext(...)
       |
RememberMeServices.loginSuccess(...) / event when configured
       |
AuthenticationSuccessHandler.onAuthenticationSuccess(...)
       |
302 redirect, JSON/HTTP status, or response per handler
```

**Why save the context?** The holder is normally bound to the current request/thread lifecycle. A redirect initiates a **new HTTP request**; for form login to keep the user authenticated, `SecurityContext` must be persisted via the appropriate repository, typically involving `HttpSessionSecurityContextRepository`. A `RequestAttributeSecurityContextRepository` only preserves context within the same HTTP request or dispatch.

In Spring Security 6's explicit-save model, merely calling `SecurityContextHolder.setContext(...)` in custom code does not ensure the context exists on the next request. Built-in authentication filters handle saving; custom flows must explicitly identify the repository and when `saveContext` is called. Save before the response commits or redirects so the session cookie has a chance to reach the browser.

### Success Handler and Request Cache

An unauthenticated user accessing `/profile` may be redirected to the login page. `RequestCache` can store the originally intended request; upon successful login, `SavedRequestAwareAuthenticationSuccessHandler` can send the user back to the page they tried to visit.

If there is no saved request, the handler can redirect to a default page. With `defaultSuccessUrl("/profile", true)`, the handler always prefers the fixed URL `/profile` over the saved request. A successful redirect **does not prove** the session/cookie was properly persisted: you must issue a follow-up request and verify.

### continueChainBeforeSuccessfulAuthentication

The base class provides `continueChainBeforeSuccessfulAuthentication` to allow continuing the filter chain **before** the success callback. By default, this is normally off. Enabling it without a clear reason allows downstream filters/controllers to run before the new context is saved, making the flow unpredictable. Test thoroughly if your system genuinely requires it.

## 5. After Failed Authentication: unsuccessfulAuthentication

When the provider/manager throws `AuthenticationException`, or a session authentication condition blocks completion, the filter goes through `unsuccessfulAuthentication(request, response, exception)`.

Core base-class actions:

- Clears `SecurityContextHolder` so the current request does not continue using an invalid authentication.
- Notifies `RememberMeServices.loginFail(...)` when remember-me is configured.
- Invokes `AuthenticationFailureHandler.onAuthenticationFailure(...)` to decide the status, redirect, or response.

```text
attemptAuthentication(...) / SessionAuthenticationStrategy
             |
        AuthenticationException
             |
    unsuccessfulAuthentication(...)
             |
    SecurityContextHolder.clearContext()
             |
    RememberMeServices.loginFail(...)
             |
    AuthenticationFailureHandler
             |
    302 /login?error or 401 depending on application policy
```

**There is no rule that "failed login always returns HTTP 401".** Form login usually redirects to an error page, such as `302 Location: /login?error`. A custom JSON login API can return 401, provided a failure handler is explicitly configured.

Do not expose overly distinct "account does not exist" vs "wrong password" details in user-facing responses, to avoid leaking account lists. Never log raw passwords, CSRF tokens, session IDs, or full credentials.

Clearing the holder on failure **does not automatically mean** every existing session is invalidated, all prior security contexts are permanently erased, or all devices are logged out. That is the responsibility of separate session/logout policies.

### How Does This Differ from ExceptionTranslationFilter?

`ExceptionTranslationFilter` primarily converts authentication/authorization exceptions from relevant parts of the security chain into responses via `AuthenticationEntryPoint` or an access-denied handler. Errors while processing **POST login** are normally routed by `AbstractAuthenticationProcessingFilter` itself through its failure handler. Do not conflate these two paths when analyzing 401/302/403 statuses.

## 6. Choosing the Right Extension Point

| What do you want to do? | Usually Appropriate Extension Point |
|---|---|
| Change redirect on successful login | `AuthenticationSuccessHandler` or `defaultSuccessUrl` |
| Show generic login error, return JSON 401 | `AuthenticationFailureHandler` |
| Support a new credential type | Suitable authentication filter + `AuthenticationManager`/`AuthenticationProvider` |
| Verify username/password | `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` |
| Prevent session fixation or limit concurrent sessions | `SessionAuthenticationStrategy` / session management |
| Persist context across requests | `SecurityContextRepository` and session policy |
| Record audit, monitoring | Events/listeners, handlers, or safe hooks without logging secrets |
| Protect API endpoints after login | `authorizeHttpRequests`, method security, business permission checks |

Most customizations of **redirects or response bodies** do not require subclassing `AbstractAuthenticationProcessingFilter`. Choosing the right handler preserves standard behavior for context, remember-me, and sessions.

### Short Success/Failure Handler Examples

The snippets below are **alternative configuration fragments**; do not combine them directly with the default redirect configuration in section 7's runnable example without updating the tests.

```java
.formLogin(form -> form.successHandler((request, response, authentication) -> {
    response.setStatus(200);
    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().write("LOGIN_OK");
}))
```

```java
.formLogin(form -> form.failureHandler((request, response, exception) -> {
    response.sendError(401, "Authentication failed");
}))
```

Handlers are responsible for the response and should not verify raw passwords themselves or mark an `Authentication` as authenticated. For apps returning JSON, design the full picture including sessions/cookies, CSRF, logout, error handling, and client behavior; a standalone HTTP 200 does not guarantee a sound authentication flow.

## 7. Complete Spring Boot MVC Example with formLogin

The example project uses **Spring Boot 3.3.5, Java 17+, Maven, and Boot-managed Spring Security 6**. Version choices serve only to present consistent configuration and clear test expectations; for new projects, choose a supported stable release and review migration notes.

Goals to observe:

- Public GET passes authorization without login.
- Anonymous private GET redirects to the login page.
- Valid POST login executes the authentication filter, the success handler redirects to a fixed URL, and the next request preserves context via session.
- Wrong-password POST login takes the failure branch.
- POST login missing a CSRF token is blocked **before** the filter checks the password.

### 7.1. Maven: pom.xml

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

    <groupId>example</groupId>
    <artifactId>auth-filter-flow</artifactId>
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

Do not declare separate Security/Framework module versions because they are aligned by the Spring Boot parent.

### 7.2. Entry Point

Create `src/main/java/example/authflow/AuthFlowApplication.java`:

```java
package example.authflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFlowApplication.class, args);
    }
}
```

### 7.3. REST Controller

Create `src/main/java/example/authflow/ProfileController.java`:

```java
package example.authflow;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/profile")
    public String profile(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
```

`Principal` is used only after the request has passed authorization on a URL requiring login. If role or ownership checks are needed, add matching rules; successful authentication does not automatically grant all business permissions.

### 7.4. SecurityFilterChain Configuration and Test Account

Create `src/main/java/example/authflow/SecurityConfig.java`:

```java
package example.authflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("correct-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/profile", true)
                .failureUrl("/login?error")
                .permitAll())
            .build();
    }
}
```

The sample configuration **does not disable CSRF**. `formLogin` enables form POST processing through the standard authentication filter; `GET /login` can render Spring Security's generated default page. `defaultSuccessUrl("/profile", true)` forces a redirect to `/profile` after successful login for predictable testing. The in-memory account is only a fixture; production requires proper user storage, password policies, and session management.

### 7.5. JUnit/MockMvc Integration Tests

Create `src/test/java/example/authflow/AuthenticationFlowTest.java`:

```java
package example.authflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousPrivateRouteRedirectsToLogin() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void successfulLoginPersistsAuthenticationInSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("correct-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void wrongPasswordInvokesFailureHandler() throws Exception {
        mvc.perform(formLogin().user("alice").password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void csrfFilterRejectsLoginPostWithoutToken() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "correct-password"))
            .andExpect(status().isForbidden());
    }
}
```

The `formLogin()` helper from `spring-security-test` creates a login request by convention and handles CSRF for the test. The final manual `post("/login")` request intentionally **omits the CSRF token**. All tests run through the web security filter chain thanks to `@SpringBootTest` and `@AutoConfigureMockMvc`.

Run with a compatible JDK 17+, Maven, and dependency repository/cache connectivity:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Expected**: 5 tests pass when the project is set up properly and dependencies resolve. Maven/Boot stdout varies by environment so no fixed transcript is shown; this is an expected result, not a claim that commands were run here. With the server running on default port 8080, visiting `http://localhost:8080/login`, signing in with fixture `alice / correct-password`, and opening `/profile` returns the exact body:

```text
Hello, alice
```

This is the controller's output for a valid logged-in session; login page HTML, cookies, and response headers depend on actual configuration.

**Why does the test use `formLogin` instead of `@WithMockUser`?** `@WithMockUser` installs a mock principal for a test and is useful for testing authorization, but it does not prove that `UsernamePasswordAuthenticationFilter.attemptAuthentication` and the provider actually ran with real passwords.

## 8. When a Custom Filter Is Truly Needed

Create a new filter only when you need a credential-collection and verification mechanism not supported by existing filters. Then you must define the request matcher, `AuthenticationManager`, session strategy, repository, success/failure handlers, and filter order. You can override these hooks:

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) throws AuthenticationException {
    // Create an untrusted authentication request from validated input.
    // Call AuthenticationManager and return the authenticated Authentication.
}

@Override
protected void successfulAuthentication(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain,
        Authentication result) throws IOException, ServletException {
    // Safe auditing without printing credentials.
    super.successfulAuthentication(request, response, chain, result);
}

@Override
protected void unsuccessfulAuthentication(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException exception)
        throws IOException, ServletException {
    // Record failure safely without revealing user existence.
    super.unsuccessfulAuthentication(request, response, exception);
}
```

This is a **hook outline, not a compilable standalone Java class**: `attemptAuthentication` lacks implementation and a `return`; a real class needs imports, constructors, matcher, manager, registration, and tests. This guide does not present an incomplete custom login filter as a production solution.

Calling `super.successfulAuthentication(...)` and `super.unsuccessfulAuthentication(...)` matters: they preserve standard logic for security context, repository, remember-me, events, and handlers. If you omit `super`, you take responsibility for reproducing the entire contract; otherwise login may appear to succeed while the next request loses context.

**Do not register the same filter in both the Servlet container and the Spring Security chain** unintentionally; double registration can cause authentication to run twice. Use Spring Security's proper filter registration mechanism and test its position. An authentication filter is not the right place to dump all business authorization logic.

## 9. Common Implementation Confusions

**Confusion 1 — GET login also triggers `attemptAuthentication`.** Incorrect for standard form login. GET typically displays the form, while POST processes authentication. Check the login processing URL, method, and matcher.

**Confusion 2 — `permitAll` on POST login bypasses CSRF.** No. The CSRF filter can block the request before authentication; `permitAll` is only an authorization rule.

**Confusion 3 — If the password is right, the controller must run immediately.** Usually success is handled by the success handler via a redirect. The controller handles the request **after the redirect**; if you want a JSON response, configure an appropriate success handler.

**Confusion 4 — The success handler must save the session itself.** Saving context belongs to the authentication filter/repository flow. The handler decides the response; custom code should not scramble sessions and security context.

**Confusion 5 — Wrong password must return 401.** Form login normally returns 302 to an error page. HTTP Basic/bearer or JSON login APIs can return 401 depending on mechanism and handler.

**Confusion 6 — Putting authentication into `SecurityContextHolder` is enough for the next request.** The holder is normally cleared at the request boundary; you must save/load via the repository when a login session is needed.

**Confusion 7 — Every authentication filter extends `AbstractAuthenticationProcessingFilter`.** No. HTTP Basic, bearer tokens, OIDC/OAuth2, and other mechanisms have their own filters/processors. Concepts like `AuthenticationManager`/`SecurityContext` are shared, though integration points differ.

**Confusion 8 — Successful authentication grants access to every endpoint.** No. `AuthorizationFilter`, method security, and ownership/tenant rules still govern access.

**Confusion 9 — Disabling session fixation protection to make login work.** Never do that. Find the root cause in session or cookie policy and fix it properly; do not strip defenses due to integration bugs.

**Confusion 10 — Logging the entire `Authentication` object helps debugging.** It can expose sensitive data. Log only safe metadata, correlation IDs, normalized error types, and never log raw credentials/tokens.

## 10. Debugging Procedure and Security Checklist

1. **Identify the HTTP stack:** Spring MVC Servlet uses `HttpSecurity`/`SecurityFilterChain`; avoid confusing it with WebFlux.
2. **Inspect the actual request:** path, method, content type, username/password parameter names, CSRF token, and session cookie.
3. **Check chain and matcher:** did `FilterChainProxy` choose the chain containing the login filter, or did `securityMatcher` or `ignoring` bypass it?
4. **Trace the attempt:** did the request enter `attemptAuthentication`, is the token passed to the manager of the right type, and does a provider support it?
5. **Distinguish the three outcomes:** `Authentication` success, `null` incomplete, or `AuthenticationException` failure.
6. **Verify post-success handling:** `SessionAuthenticationStrategy`, context repository, cookies, remember-me, and success handler.
7. **Verify the failure handler:** status/redirect, how error messages are surfaced, and avoiding data leaks.
8. **Test subsequent requests:** same session and without session, private GET before/after login, wrong password, and POST missing CSRF token.
9. **Verify business permissions:** test a logged-in user lacking access to another tenant's data; that is authorization, outside password authentication's job.
10. **Enable controlled logging:** log `org.springframework.security` at DEBUG in development; avoid sensitive logs in production.

### Self-Check

**Question 1.** Why does `GET /login` show a login page without running `attemptAuthentication`?  
**Answer:** GET typically displays the form; by default, POST matches the login processing endpoint.

**Question 2.** How does `attemptAuthentication` returning `null` differ from throwing `BadCredentialsException`?  
**Answer:** `null` signals incomplete authentication; an exception triggers the failure branch.

**Question 3.** What decides the `/login?error` redirect when the password is wrong?  
**Answer:** `unsuccessfulAuthentication` delegates the outcome to the configured `AuthenticationFailureHandler`.

**Question 4.** Password is correct and a redirect is returned, yet the next request is anonymous. What to check?  
**Answer:** `SecurityContextRepository.saveContext`, session/cookies, the repository used by filters, and when the response commits.

**Question 5.** To change the success redirect, do you need to subclass `AbstractAuthenticationProcessingFilter`?  
**Answer:** Usually no; configuring `AuthenticationSuccessHandler` or `defaultSuccessUrl` is more appropriate.

**Question 6.** Does an authenticated user automatically gain permission to view another user's orders?  
**Answer:** No. Identity authentication and authorization on business objects are two separate steps.

**Remember:** `AbstractAuthenticationProcessingFilter` orchestrates **match request → attempt authentication → session strategy → success/failure → context/repository → response handler**. Understanding the right extension points enables implementing secure Servlet login flows without overlooking CSRF, sessions, access control, and HTTP responses.