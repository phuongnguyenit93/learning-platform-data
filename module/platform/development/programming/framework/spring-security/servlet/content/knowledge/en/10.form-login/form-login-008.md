# `failureUrl`, `failureHandler`, and Messages That Do Not Leak Account Status in Spring Security

## 1. Objectives and Scope

In a **Spring Boot/Spring Security Servlet** application using **form login**, users typically submit username/password via a `POST /login` form. Login can fail for many reasons: wrong password, nonexistent username, locked account, disabled account, expired account, expired credentials, or an authentication backend failure. Spring Security must handle failures smoothly for UX **without accidentally leaking internal account state** to an unverified caller.

Two directly related extension points:

- **`failureUrl(...)`**: a concise way to declare a URL the browser redirects to after **authentication fails**.
- **`failureHandler(...)`**: provides an `AuthenticationFailureHandler`, allowing custom response handling (redirect, status, generic message), audit/metrics, or other logic within security boundaries.

Common examples:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureUrl("/login?error")
    .permitAll()
);
~~~

Or using a custom handler:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureHandler(authenticationFailureHandler)
    .permitAll()
);
~~~

These are **two alternative options**, not settings to declare simultaneously. These snippets are configuration fragments; a runnable project is in section 7.

**Security principle of this lesson:** separate **internal** failure reasons from **publicly displayed** information. A login form should never return messages usable for account enumeration such as "this username exists but is locked" or "your account has expired" to someone who has not proven ownership of the account. The UI should normally show **a generic message**; the system can record detailed reasons in a protected audit channel.

This lesson focuses on form login in the **Servlet stack** with `SecurityFilterChain`, `HttpSecurity`, `UsernamePasswordAuthenticationFilter`, and Spring Security 6.x. Non-form APIs, such as a resource server validating JWTs, follow different flows and should not blindly apply form-login redirects to API clients.

## 2. Form Login Flow and Failure Handling Point

A typical model:

~~~text
Browser
  |
  | GET /login
  v
HTML page with username/password form + CSRF token
  |
  | POST /login (username, password, CSRF token)
  v
Spring Security FilterChainProxy
  |
  v
UsernamePasswordAuthenticationFilter
  |
  +-- creates unauthenticated Authentication
  |
  v
AuthenticationManager -> AuthenticationProvider
  |
  +-- authentication succeeds
  |      |
  |      v
  |   Success handler: session/context, saved request, redirect...
  |
  +-- throws AuthenticationException
         |
         v
    AuthenticationFailureHandler
         |
         +-- default/simple: redirect to failureUrl
         |
         +-- custom: generic response, audit, metrics...
                |
                v
         Browser receives outcome without seeing internal state
~~~

This is a conceptual diagram. With session configuration, the success flow also handles CSRF/session fixation/security context as configured in Spring Security. Do not rewrite the entire standard flow just to change one error message line.

### Authentication Failure vs. Authorization Failure

- **Authentication failure**: the authenticator rejects username/password or account state. Usually throws `AuthenticationException` during login, invoking `AuthenticationFailureHandler`.
- **Authorization failure**: the user is already logged in yet lacks permission to call a URL or perform an action (e.g., missing `ROLE_ADMIN`). Denials when accessing resources are normally handled by `AccessDeniedHandler`/`ExceptionTranslationFilter`, **not** `formLogin().failureHandler(...)`.
- **CSRF failure**: missing/invalid CSRF token on POST can be rejected before `UsernamePasswordAuthenticationFilter` checks credentials. A 403 from CSRF **does not necessarily** pass through the authentication failure handler.

Therefore, do not expect `failureUrl` to handle every 401/403 across the application.

## 3. `failureUrl`: Simple Redirect on Login Failure

With form login:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/public").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .failureUrl("/login?error")
            .permitAll()
        )
        .build();
}
~~~

This snippet belongs inside a Spring `@Configuration` class with appropriate imports; it does not yet include the application class or templates.

Explanation of URLs:

- `loginPage("/login")` specifies the HTML page the browser loads via `GET /login`. When declaring a custom login page, **you are responsible for creating the controller/view** for that URL. Spring Security stops generating its default login page for custom URLs.
- `loginProcessingUrl("/login")` tells the filter to accept login requests at `POST /login`. Normally you **do not need** an MVC `@PostMapping("/login")` controller with standard form login; the filter runs before MVC.
- `failureUrl("/login?error")` is the redirect destination after authentication fails.
- `permitAll()` allows access to the login/login-error URLs; meanwhile `authorizeHttpRequests` rules should align with custom paths.
- The `?error` query is only a **generic flag telling the UI to show an error**. It does not say "locked," "disabled," or "usernameNotFound."

### How Does `failureUrl` Respond?

In a normal browser flow, failed authentication causes the handler to redirect (usually HTTP **302**) to `/login?error`. The browser then requests `GET /login?error` and re-renders the form page. With a custom view, you can display:

> Invalid username or password. Please check and try again.

This message **is kept identical for all applicable failure causes**, including locked/expired accounts or nonexistent usernames. A generic message prevents many forms of user enumeration, though it alone does not prevent every leak channel (such as timing).

### `failureUrl` Is a Convenience Config for a Failure Handler

Behaviorally, `failureUrl(...)` sets up redirect-style failure handling, typically via `SimpleUrlAuthenticationFailureHandler`. It is not a separate standalone filter added to the chain.

Spring Security may store `AuthenticationException` in the request/session for certain failure/redirect patterns. **Never expose `exception.message`, `SPRING_SECURITY_LAST_EXCEPTION.message`, or the exception class name in HTML** merely because they exist in server-side context. Exception messages can explicitly state that an account is locked, disabled, expired, or nonexistent.

Never put failure reasons into the query string like:

~~~text
/login?error=ACCOUNT_LOCKED
/login?error=USER_NOT_FOUND
/login?error=CREDENTIALS_EXPIRED
~~~

That is an anti-pattern for public login screens. Query strings can leak through browser history, shared URLs, reverse proxy logs, and analytics, while helping attackers classify accounts.

## 4. `failureHandler`: Controlled Behavior Extension

`AuthenticationFailureHandler` has one primary method:

~~~java
void onAuthenticationFailure(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException exception
) throws IOException, ServletException;
~~~

The interface lives in package `org.springframework.security.web.authentication`. The handler is invoked when **the associated filter's authentication attempt fails**. The `exception` parameter carries the technical cause, often distinguishing `BadCredentialsException`, `LockedException`, `DisabledException`, `CredentialsExpiredException`, etc. Yet those details **must not be echoed verbatim** in responses to unverified callers.

Choose a custom handler when you need to:

- Write **internal audit/metrics** with proper authorization and sensitive-data protection.
- Standardize failure responses to match company UI conventions.
- Perform generic redirects, handle AJAX requests, or serve specific clients.
- Integrate login-attempt counters/rate limiting per custom design.
- Transition to an account recovery support flow **after identity verification**, rather than announcing causes publicly.

### Simple Handler Reusing Built-in Redirect Logic

~~~java
@Bean
AuthenticationFailureHandler formFailureHandler() {
    SimpleUrlAuthenticationFailureHandler redirect =
        new SimpleUrlAuthenticationFailureHandler("/login?error");

    return (request, response, exception) -> {
        // Internal audit/metrics if genuinely needed; avoid logging passwords.
        redirect.onAuthenticationFailure(request, response, exception);
    };
}
~~~

This is a Spring bean snippet; the full project is in section 7. `SimpleUrlAuthenticationFailureHandler` handles redirects and can manage exception attributes per configuration. The handler above still redirects to **the same generic URL**, without distinguishing account status.

When a **genuine** JSON response is needed for non-browser-form clients:

~~~java
// Illustrative sample for a purpose-built authentication endpoint.
AuthenticationFailureHandler jsonFailureHandler =
    (request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write(
            "{\"error\":\"AUTHENTICATION_FAILED\"}");
    };
~~~

This is an alternative snippet, **not** wired simultaneously onto section 7's browser form login. It only handles authentication exceptions; it does not handle invalid CSRF tokens or general authorization errors. For APIs, dedicated API authentication mechanisms/entry points are usually preferable to twisting form-login redirects.

### Choosing `failureUrl` vs. `failureHandler`?

| Need | Start with |
| --- | --- |
| Ordinary form login, only needing `/login?error` and a generic message | `failureUrl("/login?error")` |
| Generic redirect + non-sensitive audit/metrics | `failureHandler(...)` delegating to `SimpleUrlAuthenticationFailureHandler` |
| JSON response from a dedicated authentication endpoint | Custom `AuthenticationFailureHandler` or suitable API authentication mechanism |
| Distinguishing exceptions to tell strangers "account locked" | **Avoid**; design an identity-verified recovery flow instead |
| 403 authorization responses on logged-in endpoints | `AccessDeniedHandler`/authorization policy, not the login failure handler |

**Never configure both `failureUrl(...)` and `failureHandler(...)` expecting them to "chain sequentially."** Both control how authentication failure is handled. If extra work is needed alongside a redirect, use one handler that explicitly delegates the redirect. Keep response policies clear and tested.

## 5. Not Leaking Account State: What Is Allowed to Show?

### 5.1. Different Internal States, Identical Public Outcome

For instance, a database/Spring Security user store may produce:

| Internal cause | Common exception (`UserDetails`-based providers) | Recommended public response |
| --- | --- | --- |
| Username does not exist | `UsernameNotFoundException` may be hidden as `BadCredentialsException` | "Invalid username or password." |
| Wrong password | `BadCredentialsException` | Same generic message |
| User locked | `LockedException` | Same generic message |
| User disabled | `DisabledException` | Same generic message |
| Account expired | `AccountExpiredException` | Same generic message |
| Credentials expired | `CredentialsExpiredException` | Same generic message |

`DaoAuthenticationProvider`/`AbstractUserDetailsAuthenticationProvider` typically checks account status before/after password verification per its workflow. The exceptions above are **details of username/password mechanisms**, not automatically applicable to every `AuthenticationProvider` or bearer token.

Internal states help operations and support troubleshoot properly; external responses should avoid confirming which accounts exist or their specific condition.

### 5.2. Why Do Detailed Errors Create a User Enumeration Channel?

Suppose a public login returns:

~~~text
alice@example.com  -> "Wrong password"
bob@example.com    -> "Account does not exist"
admin@example.com  -> "Account is locked"
~~~

An attacker can submit many usernames and classify which accounts exist, who is locked, and which accounts might have a matching password. This compounds other leak channels such as differences in HTTP status, body, redirect location, processing time, or response size.

**Practical goal:** for failures meant to remain hidden, unify public messages, status codes, and redirect targets; minimize unnecessary differences in timing/side effects, and add rate limiting, monitoring, and anti-credential-stuffing controls. **A generic message alone does not guarantee protection against timing-based enumeration.**

When legitimate users need to know their account is locked/expired or requires a password change, design a **post-ownership-verification support/recovery flow**: e.g., sending an out-of-band email with appropriate info, MFA/step-up where available, or verified helpdesk workflows. Never display account existence/status on the unverified UI.

### 5.3. Never Use `exception.message` Directly in Templates

An example **to avoid**:

~~~html
<!-- Anti-pattern: leaks failure reason from internal exception -->
<p th:text="${session.SPRING_SECURITY_LAST_EXCEPTION.message}"></p>
~~~

Pattern **to use**:

~~~html
<p th:if="${param.error}" role="alert">
  Invalid username or password.
</p>
~~~

Both snippets use Thymeleaf syntax for templates; `param.error` only checks the generic flag. Never display, forward, or reflect raw exception text from `AuthenticationFailureHandler`.

Some older tutorials suggest displaying `SPRING_SECURITY_LAST_EXCEPTION.message` for easy debugging; that violates the requirement **not to leak account status** on a public login page.

### 5.4. Audit Internally Without Logging Secrets

Auditing helps detect anomalous login attempts, investigate incidents, and enforce compliance. However, audit logs must be access-controlled, data-minimized, and governed by retention policies. Never log:

- Raw passwords or `password` field values.
- `Authorization` headers, session cookies, tokens, or CSRF tokens.
- Full authentication exception/message text if it may carry sensitive info.
- Full usernames/IPs in broad logs without a privacy and access-control basis.

If error-type metrics are needed, use standardized internal labels with bounded cardinality, hidden from end users. Never attach unbounded per-username labels and accidentally create high-cardinality metric explosions or a new sensitive-data store.

## 6. Connections to CSRF, Saved Requests, Sessions, and Paths

### 6.1. Form Login Requires POST and a Valid CSRF Token

Spring Security Servlet form login normally receives `POST /login` via `UsernamePasswordAuthenticationFilter`, with default parameters `username` and `password`. When CSRF is enabled (default in standard web configs), the POST request needs a valid CSRF token.

If the token is missing/invalid, the request can receive **403 Forbidden** from the CSRF filter and **never** invoke `AuthenticationFailureHandler`. That is not evidence that the username is locked or the password is wrong. Never disable CSRF just to "fix" form errors; verify the form has the hidden CSRF field and matching cookie/session.

In Thymeleaf integrated with Spring MVC, you can use:

~~~html
<form th:action="@{/login}" method="post">
  <input type="text" name="username">
  <input type="password" name="password">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Sign in</button>
</form>
~~~

This snippet explicitly shows the CSRF field. When using `th:action` with Spring MVC/Thymeleaf integration, the framework can automatically inject a hidden CSRF field; if a template also renders an explicit CSRF field, avoid emitting two conflicting values. Section 7's complete example uses a properly wired form and `_csrf` attribute.

### 6.2. The Login Page Must Be Accessible Without Logging In

If you configure `loginPage("/login")` yet `GET /login` also requires authentication under policy, the browser can enter a redirect loop. Use `formLogin(...).permitAll()` and ensure authorization matchers cover the login page, assets, and `/error`.

When customizing `loginProcessingUrl`, the HTML form must submit to the matching action/method. Submitting `POST /signin` by mistake when the filter only listens on `POST /login` can route the request to MVC/CSRF/error handlers instead of the authentication filter; in that case `failureHandler` is never called.

### 6.3. Success Redirect Differs from Failure Redirect

After successful login, Spring Security can send the user to a prior **saved request** or default target URL. On failure, `failureUrl` redirects to a generic error page. Do not confuse `defaultSuccessUrl(...)` or `successHandler(...)` with the failure handler.

If using client-supplied redirect URLs, check for open redirects; for standard form login, using a **fixed internal error destination** such as `/login?error` is simpler and safer.

### 6.4. Session Exceptions Are Not Public Messages

Some failure handlers can store the exception in the session/request. That helps internal customization, yet it does not make the message safe to render in the UI. Keeping exceptions or account-state details longer than necessary can also leave stale data in sessions and widen sensitive surface area. For user-facing UI messages, rely strictly on **a generic error flag** or a non-leaking error code.

### 6.5. Rate Limiting and Account Lockout Can Be Abused

Locking an account after too many failures slows brute force, yet attackers can abuse it to cause **denial of service** against other users' accounts. Combine multi-signal throttling, risk-based controls, monitoring, MFA, and safe unlock/recovery policies. `failureHandler` can assist with event recording, yet it **does not automatically provide** failure counting or account lockout unless the application implements them.

## 7. Runnable Spring Boot 3 / Spring Security 6 Example

The example below demonstrates **a custom `AuthenticationFailureHandler`** that always redirects to `/login?error`, while a Thymeleaf page displays only **a generic message**. It works across valid users, wrong passwords, nonexistent users, locked, disabled, and expired accounts. It preserves default CSRF, reveals no exception details, and includes MockMvc tests.

**Design points:**

- Spring Boot 3.3.x, Java 17+, Spring MVC + Thymeleaf + Spring Security.
- `/login` is a self-provided HTML page; `POST /login` is handled by Spring Security's filter.
- Form login uses a custom `failureHandler`, delegating the generic redirect to `SimpleUrlAuthenticationFailureHandler("/login?error")`.
- The login page never prints exceptions/messages; it shows one non-specific string whenever the URL contains `?error`.
- `InMemoryUserDetailsManager` is for demo only; the account flags test behavior, not production user management.
- Tests verify multiple failure modes all produce the same redirect and same message. HTTP status on the POST response is typically **302**, followed by **200** on the login page GET.

### 7.1. Directory Structure

~~~text
form-login-failure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/loginfailure/
    │   │   ├── LoginFailureApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── LoginController.java
    │   │   └── HomeController.java
    │   └── resources/templates/login.html
    └── test/java/com/example/loginfailure/LoginFailureTests.java
~~~

**`pom.xml`:**

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
    <artifactId>form-login-failure</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

**`src/main/java/com/example/loginfailure/LoginFailureApplication.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/loginfailure/SecurityConfig.java`:**

~~~java
package com.example.loginfailure;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class SecurityConfig {

    private static final Logger log =
        LoggerFactory.getLogger(SecurityConfig.class);

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler formFailureHandler
    ) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureHandler(formFailureHandler)
                .permitAll()
            )
            .build();
    }

    @Bean
    AuthenticationFailureHandler formFailureHandler() {
        SimpleUrlAuthenticationFailureHandler redirect =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            // Minimal example: do not log username/password/exception.
            // Production can emit non-sensitive internal events.
            log.warn("Form sign-in failed");
            redirect.onAuthenticationFailure(request, response, exception);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("active")
                .password(hash)
                .roles("USER")
                .build(),

            User.withUsername("disabled")
                .password(hash)
                .roles("USER")
                .disabled(true)
                .build(),

            User.withUsername("locked")
                .password(hash)
                .roles("USER")
                .accountLocked(true)
                .build(),

            User.withUsername("accountExpired")
                .password(hash)
                .roles("USER")
                .accountExpired(true)
                .build(),

            User.withUsername("credentialsExpired")
                .password(hash)
                .roles("USER")
                .credentialsExpired(true)
                .build()
        );
    }
}
~~~

**Code note:** all users share the same BCrypt-encoded demo password; user `active` has four valid status flags, while the other four are rejected for their respective reasons. The handler does not distinguish statuses in responses. The demo lacks wrong-password counting or auto-locking; flags are preset for testing.

**`src/main/java/com/example/loginfailure/LoginController.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginController {
    @GetMapping("/login")
    public String login() {
        return "login";
    }
}
~~~

This controller only handles **GET** for the login page; POST is handled by the Spring Security filter. `@Controller` returns a Thymeleaf view name, not a `@RestController` returning a raw body string.

**`src/main/java/com/example/loginfailure/HomeController.java`:**

~~~java
package com.example.loginfailure;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {

    @GetMapping("/public")
    public String publicPage() {
        return "public OK";
    }

    @GetMapping("/")
    public String home(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile: " + authentication.getName();
    }
}
~~~

`/public` is viewable while unauthenticated; `/` and `/profile` require authentication. When login succeeds without a prior saved request, Spring Security usually redirects to `/`.

**`src/main/resources/templates/login.html`:**

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign in</title>
</head>
<body>
    <h1>Sign in</h1>

    <p th:if="${param.error}" role="alert">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>

    <form method="post" th:action="@{/login}">
        <label for="username">Username</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <button type="submit">Sign in</button>
    </form>
</body>
</html>
~~~

The HTML page **does not read `exception.message`**, nor does it take an exception class from the query string; it only checks whether the `error` flag is present and shows a fixed message. `th:action="@{/login}"` is resolved by Thymeleaf with context path support; the CSRF token comes from Spring Security's request attribute. In some Thymeleaf/Spring MVC configurations, `RequestDataValueProcessor` may also auto-add a hidden CSRF field when using `th:action`; inspect the actual rendered HTML to avoid duplicate fields with different values. Having both carry a valid token does not alter CSRF protection principles.

### 7.2. Testing with Spring Security MockMvc

Regression tests are essential because a generic message can accidentally be replaced by an exception message during a later template edit.

**`src/test/java/com/example/loginfailure/LoginFailureTests.java`:**

~~~java
package com.example.loginfailure;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allAccountFailuresUseSameRedirect() throws Exception {
        for (String username : List.of(
                "disabled",
                "locked",
                "accountExpired",
                "credentialsExpired",
                "unknown-user"
        )) {
            mvc.perform(formLogin()
                    .user(username)
                    .password("demo-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
        }

        mvc.perform(formLogin()
                .user("active")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void publicPageOnlyShowsGenericFailureMessage() throws Exception {
        mvc.perform(get("/login?error"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Tên đăng nhập hoặc mật khẩu không hợp lệ.")))
            .andExpect(content().string(
                not(containsString("LockedException"))))
            .andExpect(content().string(
                not(containsString("DisabledException"))));
    }

    @Test
    void validUserCanSignIn() throws Exception {
        mvc.perform(formLogin()
                .user("active")
                .password("demo-pass"))
            .andExpect(authenticated().withUsername("active"));
    }
}
~~~

**Test explanation:**

- `SecurityMockMvcRequestBuilders.formLogin()` builds a Spring Security login POST with appropriate parameters and CSRF token, avoiding mistaking a missing-CSRF 403 for a credentials failure.
- Six cases—wrong password, nonexistent user, disabled, locked, expired account, and expired credentials—must all return **the same `/login?error` redirect**.
- `GET` of the error page must render the fixed message without exposing exception classes. This is a basic output test; **it does not prove immunity against all side channels**.
- User `active` with the right password must authenticate successfully.
- If the app also has API authentication policies, write separate tests for status/JSON instead of forcing API clients to follow web form redirects.

### 7.3. Running and Observing

Requires Maven, JDK 17+, and network access to download dependencies on the first run. In the directory with `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Expected result: `mvn test` finishes with **BUILD SUCCESS** if the project is created properly and dependencies are downloaded; test counts/logs depend on the runner machine. This example is code designed to run, **not Maven output captured here**.

Open `http://localhost:8080/login`. Try logging in:

| Username | Password | Expected after POST |
| --- | --- | --- |
| `active` | `demo-pass` | Succeeds, enters protected page |
| `active` | wrong | Redirect `/login?error`, generic message |
| `unknown-user` | `demo-pass` | Identical redirect |
| `disabled` | `demo-pass` | Identical redirect |
| `locked` | `demo-pass` | Identical redirect |
| `accountExpired` | `demo-pass` | Identical redirect |
| `credentialsExpired` | `demo-pass` | Identical redirect |

**Note:** `unknown-user` is not an account in `InMemoryUserDetailsManager`. All other users are demo accounts. The UI should not reveal which failure type occurred.

Quick check with `curl`:

~~~bash
curl -i http://localhost:8080/public
# Expected HTTP 200, body: public OK

curl -i http://localhost:8080/profile
# Expected HTTP 302, Location redirecting to /login

curl -i http://localhost:8080/login
# Expected HTTP 200, HTML with username/password form and CSRF token

curl -i 'http://localhost:8080/login?error'
# Expected HTTP 200, page with generic error message
~~~

To properly **POST** a login with `curl`, obtain the CSRF token and preserve the cookie/session from the GET form, then submit that token back. Do not run `curl -d username=...` without CSRF and claim the 403 is a password error. For this demo, a browser and `MockMvc` are more convenient to verify standard behavior.

### 7.4. How to Simplify If Only `failureUrl` Is Needed?

Replace the handler configuration in `SecurityConfig` with:

~~~java
.formLogin(form -> form
    .loginPage("/login")
    .loginProcessingUrl("/login")
    .failureUrl("/login?error")
    .permitAll()
)
~~~

This is an **alternative variant** of the `.formLogin(...)` section in the `SecurityFilterChain` bean. With this variant, the `formFailureHandler()` bean no longer needs to be injected into the chain. Do not place both options in the same configuration expecting both to apply. The Thymeleaf template and generic message rule remain unchanged.

## 8. Auditing, Logging, and Managing Internal Failure Reasons

### 8.1. Separating Public Messages from Internal Reason Codes

One way to divide responsibilities:

~~~text
AuthenticationProvider
    |
    +-- produces internal AuthenticationException
            |
            v
AuthenticationFailureHandler
    |
    +-- Controlled audit/metrics
    |      -> standardized reason code, no raw secrets
    |
    +-- Public response
           -> /login?error
           -> "Invalid username or password."
~~~

You can consider internal event codes like `BAD_CREDENTIALS`, `ACCOUNT_DISABLED`, `ACCOUNT_LOCKED`; however, **never push those codes into URLs/queries/bodies returned to unauthenticated clients**, and avoid over-collecting personal data in observability.

`AuthenticationFailureHandler` is not necessarily the sole best place for all auditing; Spring Security also offers authentication events and event publisher integration. Choose an event mechanism that preserves detail across multiple provider types without introducing vulnerabilities when logging events or when audit backends fail.

### 8.2. Dangerous Logging Patterns

~~~java
// DO NOT do this:
log.warn("Login failed for {} with password {}: {}",
    username, rawPassword, exception.getMessage());

// Minimal approach, leaking no login details:
log.warn("Form sign-in failed");
~~~

This snippet illustrates logging only, not a standalone program. When you need to know which account is under attack, consider pseudonymization, access-controlled logs, short retention, SIEM setup, and compliance duties. Never treat "internal" logs as a place to freely dump passwords or session tokens.

### 8.3. Do Not Leak User Existence Through Side Channels

Even when responses share one URL, user enumeration can still happen if:

- Existing users incur slow BCrypt hashing while nonexistent users return immediately; or an account status is rejected before password checking.
- Response bodies/headers/cookies differ noticeably by reason.
- Password-reset or email-verification endpoints return different responses when a username exists.
- Rate-limit counters, CAPTCHAs, or account lockouts exhibit predictable behavioral differences.
- Account-state errors surface in a different URL or post-redirect message.

You cannot claim a system achieves **constant-time login** merely by using one failure handler. Threat modeling, rate limiting, response testing, reducing unnecessary timing differences, and live monitoring are required. Some provider mechanisms mitigate timing leaks for nonexistent usernames, yet never blindly rely on that across every account state and custom provider.

## 9. Cases Where the Same Policy Should Not Apply

### 9.1. Sign-In After Identity Verification

Once a user completes a trusted verification step (such as email verification or a recovery token tightly bound to the account), the support UI can provide more specific guidance: the account needs unlocking, the password needs changing, or the user should contact support. This is a **post-verification flow**, not immediate feedback on the public login form. For sensitive states, consider sending notices through verified channels and scoping token lifetimes tightly.

### 9.2. APIs and Form Login Do Not Share the Same Response Style

API clients typically want **401 + JSON** or a scheme-appropriate challenge rather than `302 /login?error`. In hybrid web + API systems, use separate `SecurityFilterChain` beans or suitable entry points/authentication filters. A `failureHandler` attached to `formLogin` does not automatically handle HTTP Basic/JWT failures on an API chain. Never use one redirect handler for every mechanism and make API clients hard to debug.

### 9.3. System Failures Differ from Credential Failures

If a database or identity provider suffers an outage, that is a system failure rather than a wrong password. Public responses still must not leak stack traces, SQL, user records, or secrets. Still, you do not have to disguise every outage as `?error`: you can return a generic "Service temporarily unavailable" message for widespread outages with appropriate HTTP status and observability. Design based on exception mapping and availability, rather than catching every `Exception` and masking bugs.

### 9.4. CSRF / Authorization 403

A `POST /login` missing a CSRF token can be handled by `AccessDeniedHandler` and return 403. It is not a "disabled account" signal. Do not feed CSRF failures into wrong-password lockout counters unintentionally, or legitimate users could get locked out due to missing browser tokens or misconfigured clients.

## 10. Checklist for Real Projects

**Form login configuration**

- Explicitly define `loginPage`, `loginProcessingUrl`, `failureUrl` or `failureHandler`, and success behavior.
- Permit pre-login access to the login page and required assets; avoid redirect loops.
- Keep CSRF enabled appropriately for login forms and sessions; test hidden tokens.
- In custom failure handlers, **never** reflect `AuthenticationException.message` into public responses.
- Use a single fixed error URL or generic JSON code; never place account states into query strings.

**Account security**

- Wrong password, nonexistent username, locked, disabled, and expired must produce **consistent public feedback** before identity verification.
- Avoid leaking user status unnecessarily via secondary responses, reset links, headers, payload sizes, or timing.
- Design brute-force/credential-stuffing defenses, rate limits, MFA/step-up, session controls, and alerting.
- Build recovery flows after **verifying account ownership** to assist legitimate users.

**Observability and testing**

- Audit with access control, never logging passwords/secrets/tokens; limit username/IP logging per policy.
- Test failed POST responses and error page GETs, not only valid username/password logins.
- Test missing CSRF separately; test authorization 403 separately.
- Test login success, saved requests, logout, and verifying no account state leaks in HTML.
- When swapping providers or adding SSO/OIDC/2FA, re-audit exception types and failure paths; do not assume one handler catches everything.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Rendering `exception.message` on the login page | Leaks disabled/locked/expired, aids username enumeration | Render only a generic error string keyed off `?error` |
| Setting `failureUrl("/login?locked")` per exception | Leaks state in URLs/logs | Redirect to fixed `/login?error` |
| Declaring custom `loginPage` without creating GET view | 404 or redirect loop | Create MVC controller + template for the login page |
| Creating `@PostMapping("/login")` expecting standard filter not to interfere | Duplicate/conflicting flows | Choose one login POST handler, usually the standard filter |
| Forgetting CSRF token on form POST | 403 bypassing failure handler | Send the CSRF token instead of disabling CSRF |
| Setting both `failureUrl` and `failureHandler` without clear precedence | Unexpected behavior | Use a single handler or only `failureUrl` |
| Returning different messages for nonexistent username vs. wrong password | User enumeration | Use identical generic feedback and test it |
| Logging raw passwords or full `AuthenticationException` | Sensitive data leak | Minimal auditing, access control, secret filtering |
| Assuming `failureHandler` handles every HTTP 403 | Wrong for authorization/CSRF | Check `AccessDeniedHandler` and CSRF handling separately |
| Auto-locking accounts solely inside a custom handler | Lacks state store/atomic updates/rate limits | Design a complete anti-brute-force policy |
| Assuming all form failures should return JSON | Breaks browser UX | Forms redirect; APIs respond per API contract |
| Checking only status 302 without checking URL and HTML | Reasons can still leak in query/page | Assert redirect location, view content, and side channels |

## 12. Self-Check Questions

**1. What does `failureUrl("/login?error")` handle?**

It configures where to redirect after form login authentication fails. The browser typically receives a redirect to that URL and reloads the login page, where the UI shows a generic error message.

**2. When should you use `failureHandler(...)` instead of `failureUrl(...)`?**

When you need a custom response, audit/metrics, or extra failure-handling logic. If still redirecting, delegate to `SimpleUrlAuthenticationFailureHandler` to avoid reimplementing low-level details.

**3. Why should `exception.getMessage()` not be shown on the login form?**

The message can expose account status, username existence, or technical details; attackers can use that for account enumeration. Show only a generic message to unverified callers.

**4. When a user hits `LockedException`, should you redirect to `/login?error=locked`?**

Not on public login. Keep responses identical to wrong username/password; move unlock notifications into an ownership-verified recovery flow.

**5. If `POST /login` returns 403 due to a missing CSRF token, is `failureHandler` always called?**

No. The CSRF filter can reject before credential verification. Identify where the error originated and fix the CSRF token/request instead of blaming account status.

**6. Does using the same redirect and message completely prevent enumeration?**

No. Timing, secondary responses, password-reset endpoints, rate-limit behavior, or misconfigurations can still leak. Threat modeling and defense-in-depth are required.

**7. Why is Spring Security's `formLogin()` test helper useful?**

It submits a properly formatted login request with a CSRF token when needed, letting you accurately test authentication failures instead of accidentally testing a missing-CSRF 403.

**8. Does `failureHandler` control access to `/admin` after login?**

No. It handles authentication failure within the login flow; it does not replace `authorizeHttpRequests`, `AccessDeniedHandler`, or method security.

**9. When can you direct a user to a password-change page?**

After a trusted identification/verification step and under a secure policy. Never use distinct errors on a public form to confirm a specific account has expired credentials.

**10. In the runnable example, why do disabled/locked/expired users all see the same error page?**

Because the custom failure handler always redirects to `/login?error`, and Thymeleaf only checks the `param.error` flag to display a fixed string; the specific `AuthenticationException` reason is never publicized.

**Key takeaway:** **`failureUrl` is the quick way to redirect after a form login error; `failureHandler` enables more flexible handling. Either way, keep public messages generic, never render exceptions or account status to unverified users, and distinguish authentication failures from CSRF/authorization failures.**