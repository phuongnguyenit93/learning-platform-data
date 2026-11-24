# failureUrl, failureHandler, and Login Messages That Do Not Disclose Accounts

In a **Spring Security Servlet application using form login**, when a user submits invalid credentials, authentication can fail inside `AuthenticationManager` or `AuthenticationProvider`. Spring Security should not expose raw internal causes such as "username not found", "wrong password", "account disabled", or exception details to the browser: doing so enables attackers to **enumerate valid accounts (account/username enumeration)** and optimize password-guessing campaigns.

Two extension points directly tied to the login failure experience are:

- **`failureUrl("/login?error")`**: a concise configuration option that typically redirects to a fixed URL so the UI displays a **generic message**.
- **`failureHandler(AuthenticationFailureHandler)`**: provides full control over the response after an authentication failure in the authentication filter—such as controlled redirects, returning `401` JSON to clients, or writing filtered internal audit logs.

This lesson belongs to the **Form Login** group and covers the failure flow in `UsernamePasswordAuthenticationFilter`, the relationship between `failureUrl` and `failureHandler`, preventing account disclosure via body/status/redirects/timing, login page configuration, CSRF handling, sessions, user experience, security testing, and a **standalone runnable Java 17** example simulating responses with real Spring Security APIs.

**Foundational principle:** Telling users **"Unable to sign in; please check your credentials or use account recovery"** is sufficient in most cases. Operational systems may distinguish deeper causes **on protected internal channels**, but never use public responses to confirm that an account name exists.

## 1. Where Does Form Login Fail?

Typical flow with Spring Security 6, Java Servlet:

~~~text
Browser
  |
  |  POST /login
  |  username=...&password=...&CSRF=...
  v
SecurityFilterChain
  |
  +--> CsrfFilter (if CSRF is enabled)
  |      |-- missing/invalid -> 403 before form auth filter
  |
  '--> UsernamePasswordAuthenticationFilter
          |
          +--> Read username/password by parameter names
          +--> Create UNTRUSTED Authentication
          +--> AuthenticationManager.authenticate(...)
          |      |
          |      +--> DaoAuthenticationProvider
          |             +--> UserDetailsService.loadUserByUsername
          |             +--> PasswordEncoder.matches
          |             +--> Check account/credential status
          |
          +-- SUCCESS -> SecurityContext, session strategy,
          |              configured successHandler
          |
          '-- FAILURE -> AuthenticationException
                           |
                           +--> Never turn failed auth into trusted principal
                           +--> remember-me failure hook if present
                           '--> AuthenticationFailureHandler
                                    |
                                    +--> Redirect /login?error
                                    '--> Or fixed 401 JSON response
~~~

This diagram is **conceptual**, not framework source code. Actual steps and lifecycle also depend on the security chain, session, authentication filter, remember-me, and Spring Security version. Crucially: **the authentication failure handler is not where raw passwords are verified**; that belongs to `AuthenticationManager`/providers and `PasswordEncoder`.

### 1.1. What Errors Fall Under AuthenticationException?

Common subclasses:

| Exception | Internal meaning | Should it be shown verbatim? |
|---|---|---|
| `BadCredentialsException` | Invalid authentication proof | **No** |
| `UsernameNotFoundException` | `UserDetailsService` could not find account | **No** |
| `DisabledException` | Account is not permitted to sign in | **Do not confirm account exists** |
| `LockedException` | Account is currently locked | **Do not confirm account exists** |
| `AccountExpiredException` | Account validity period has expired | Do not disclose during public login |
| `CredentialsExpiredException` | Credentials expired per policy | Use appropriate change/reset flow after proving identity |
| `AuthenticationServiceException` | Auth processing/infrastructure error, per provider | Do not print stacktrace; alert operations |

These subclasses do not share the same root cause: `LockedException` differs from a wrong password, and a database outage differs from a nonexistent account. **The public user message may stay identical**, while internal metrics/audits/runbooks must distinguish them to troubleshoot properly without hiding system outages.

### 1.2. Do Not Confuse CSRF Errors with Password Errors

If the browser submits `POST /login` with a missing or invalid CSRF token while CSRF protection is enabled, `CsrfFilter` can reject the request **before `UsernamePasswordAuthenticationFilter` calls the provider**. Consequently, the form authentication `failureHandler` **may not run**, and the typical result is `403`.

The fix is to ensure the form supplies a valid CSRF token and test against the proper policy—**never disable CSRF app-wide** just for a nicer login redirect. For browser cookie/session applications, dropping CSRF protection can create a severe vulnerability.

## 2. What Is failureUrl and How Does It Work by Default?

Inside `formLogin`, you can write:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .failureUrl("/login?error")
            .permitAll());
    return http.build();
}
~~~

This is a **Spring Boot/Spring Security Servlet configuration snippet**, requiring imports, beans, user store/provider, Spring MVC, and a matching login page; it is not a standalone program. `failureUrl` is provided by `AbstractAuthenticationFilterConfigurer`. It configures a default handler based on **`SimpleUrlAuthenticationFailureHandler`** to redirect to the specified URL when form authentication fails.

With this setup, browsers typically observe:

~~~text
POST /login -> authentication fails
HTTP 302 Location: /login?error
GET /login?error -> re-renders form and GENERIC message
~~~

The 302 redirect status is standard behavior, while exact method/status details depend on redirect strategy, proxies, and config. After the redirect, the URL only signals that **the previous login attempt failed**—**not whether the username exists or the account is locked**.

### 2.1. Why Use ?error Instead of ?reason=USER_NOT_FOUND?

`/login?error` is a generic flag sufficient for the UI to show fixed text. The URLs below **must not be used** for public login:

~~~text
/login?error=USERNAME_NOT_FOUND
/login?error=PASSWORD_WRONG
/login?error=ACCOUNT_DISABLED
/login?reason=locked&username=linh
/login?message=Invalid%20password%20for%20linh
~~~

Even if the UI hides the text, differing query strings can be observed in browser history, reverse proxy logs, analytics, Referer headers, or automated scripts. They also leak information to attackers spraying millions of usernames.

A generic redirect URL alone does not guarantee safety: if the HTML body, cookies, HTTP status, latency, or recovery endpoints vary systematically with account existence, **username enumeration still occurs**.

### 2.2. failureUrl Is Not an Automatically Generated Custom Page

When calling `loginPage("/login")`, **the application is normally responsible for serving GET `/login`** (e.g., via controller + Thymeleaf). `loginProcessingUrl("/login")` specifies the **POST** URL handled by the authentication filter. Both endpoints may share a path yet differ in method and function.

If a `SecurityFilterChain` applies `securityMatcher("/secured/**")` while the login page/processing URL `/login` sits outside that matcher, the form authentication filter **will not apply to `POST /login`**. The outcome is typically 404/405 or a broken flow rather than a `failureUrl` issue. Test real URLs against the exact active chain.

### 2.3. failureUrl vs. successUrl

`failureUrl` is for **failed authentication**. `defaultSuccessUrl` and `successHandler` are for **successful authentication**. Never use the failure URL to "let users continue logging in" when the provider rejected them.

To send users back to the page they tried to open, Spring Security provides request caching and success handlers. **Client-supplied redirect paths** must be validated before use to prevent open redirects or leaking data to external domains.

## 3. AuthenticationFailureHandler: Full Control Over Post-Failure Responses

Core interface:

~~~java
public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
~~~

This is an **abbreviated API signature for study**, not an interface you write yourself. The handler is invoked by the authentication filter after catching an error within its scope. Parameters:

- `request`: the failed HTTP request, which may hold raw username/password, headers, and session; **never dump/log the whole object**.
- `response`: where status/headers/body/redirect are written. The handler must return the format expected by the client and never commit twice.
- `exception`: holds the **internal** error type and message; useful for controlled auditing/logging, **never expose `getMessage()` or stacktraces directly to clients**.

### 3.1. How Do failureUrl and failureHandler Relate?

| Configuration | Purpose | Typical outcome |
|---|---|---|
| `.failureUrl("/login?error")` | Simple browser form login | Redirects to a fixed URL |
| `.failureHandler(handler)` | Custom redirect/forward/JSON/metrics | Determined by handler |
| `SimpleUrlAuthenticationFailureHandler` | Built-in implementation for URL redirect/forward | Redirects or forwards to configured URL |
| `ExceptionMappingAuthenticationFailureHandler` | Can map exception types to URLs | **Use caution**: mapping distinct public URLs by account status leaks state |
| Custom handler returning `401` | Certain AJAX/API clients | Generic status/body, no redirect |

`failureUrl` is essentially a **shortcut configuring an `AuthenticationFailureHandler`**. Do not chain `failureUrl(...)` and `failureHandler(...)` back-to-back expecting both to run together; the later setting can override the earlier handler. **Choose one clear policy** per security chain and test the actual response.

### 3.2. When to Choose failureHandler?

- Login is submitted via **fetch/AJAX** and the client expects a `401` JSON response rather than an HTML redirect.
- You need to emit **audit events** or filtered failure metrics per policy without disclosing accounts.
- You need consistent `Cache-Control`/Content-Type headers or uniform status codes.
- Multi-tenant apps selecting login pages via a **verified mapping**, never redirecting arbitrarily on client input.
- You want to skip caching `AuthenticationException` in the session on failed logins by writing a custom handler that avoids `saveException` and stacktraces.

You do not need a custom handler just to customize the error wording on the login page: with a fixed `failureUrl` and a template showing a generic message, **the default setup can be simpler and safer**.

### 3.3. Never Let exception.getMessage() Dictate the Public Message

**Wrong:**

~~~java
response.sendError(401, exception.getMessage());
~~~

Or:

~~~java
return "redirect:/login?error=" +
        URLEncoder.encode(exception.getMessage(), UTF_8);
~~~

These are **anti-examples**. `exception.getMessage()` may contain overly specific details, provider customizations, or account-tied data. Putting exceptions into URLs also pushes details into logs and browser history.

**Correct in principle:**

~~~java
response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
response.setContentType("application/json;charset=UTF-8");
response.getWriter().write(
        "{\"error\":\"Unable to sign in with the provided credentials.\"}");
~~~

This is a **code snippet inside a handler**, not a standalone class. When returning JSON with dynamic values, handle escaping properly; the example above uses a **fixed literal** without concatenating exceptions or usernames.

## 4. SimpleUrlAuthenticationFailureHandler: Redirect, Forward, and Session

Spring Security's built-in handler commonly used when configuring `failureUrl`.

### 4.1. When defaultFailureUrl Is Set

~~~java
SimpleUrlAuthenticationFailureHandler failure =
        new SimpleUrlAuthenticationFailureHandler("/login?error");
~~~

In `onAuthenticationFailure(...)`, the handler redirects to the configured `defaultFailureUrl`. If `useForward=true`, it invokes `RequestDispatcher.forward` instead of redirecting; this carries different semantics for HTTP method, request attributes, container dispatchers, and rendering.

**Do not use forward merely to avoid a redirect and assume the form gets a fresh GET.** Forwarding stays within the same request/dispatch, which can deliver unexpected methods and request bodies to controllers/templates; verify with integration tests.

### 4.2. When defaultFailureUrl Is NOT Set

Javadoc states that `SimpleUrlAuthenticationFailureHandler` without a URL sends a **`401`** error response along with the `AuthenticationException` message per implementation behavior. Given the goal of **not disclosing account details**, **do not expose that branch publicly by default** without verifying the actual message, status, and body.

Configure a fixed `failureUrl` or a custom handler returning a fixed body if API clients need 401. Verify expected results on your target framework/container version.

### 4.3. Exceptions Can Be Stored in Session or Request

An easily overlooked detail: `SimpleUrlAuthenticationFailureHandler` calls `saveException` when redirecting/forwarding to the failure URL.

- **Redirect:** usually stores `AuthenticationException` in `HttpSession` so views can inspect it; if no session exists, it may create one per `allowSessionCreation`.
- **Forward:** the exception is usually stored in a **request attribute** since it stays within the current request.
- Spring Security typically uses the attribute `WebAttributes.AUTHENTICATION_EXCEPTION`.

**Data residing in the session does not mean it should be displayed in the UI.** Templates must never read the exception message and render it, even though users can view `/login?error`. If writing a custom handler using a fixed redirect without needing exception storage, avoid calling `saveException` or clean up stale attributes per policy.

### 4.4. Session Exception vs. User's Authentication

`WebAttributes.AUTHENTICATION_EXCEPTION` only records the **failure reason**, not an authenticated principal. Never treat a session holding that attribute as logged in. If form login fails while another session already existed, inspect the relevant `SecurityContext`/session policy; do not assume the entire session was logged out simply because the failure handler ran.

Logout, session invalidation, session fixation, remember-me cleanup, CSRF, and forced reauthentication are separate lifecycle layers.

## 5. Building a Login Page That Shows Only a Generic Message

A common Spring MVC + Thymeleaf setup:

~~~java
@Controller
class LoginPageController {
    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

This snippet requires Spring MVC imports. Create template `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="en"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In</title>
</head>
<body>
    <h1>Sign In</h1>

    <p th:if="${param.error}" role="alert">
        Unable to sign in with the provided credentials.
        Please try again or use account recovery.
    </p>

    <form th:action="@{/login}" method="post">
        <label>
            Username
            <input type="text" name="username" autocomplete="username">
        </label>
        <label>
            Password
            <input type="password" name="password"
                   autocomplete="current-password">
        </label>
        <button type="submit">Sign In</button>
    </form>

    <a th:href="@{/forgot-password}">Forgot password?</a>
</body>
</html>
~~~

Thymeleaf integrated with Spring MVC/Spring Security normally inserts a **CSRF hidden field** into POST forms via `RequestDataValueProcessor`; verify the actual HTML output in your app. If not using Thymeleaf or without that integration, pass a valid CSRF token into the form appropriately. **Never hardcode a static CSRF token** and never disable CSRF just to make the form work.

The "Forgot password?" link should point to a real recovery flow protected against enumeration. That path is just a UI example; configure a controller for `/forgot-password` if you want the link active.

### 5.1. Condition for Displaying the Notice

`th:if="${param.error}"` only checks whether the flag appears in the post-redirect request. **Never render the value of `param.error` itself as the message**: an attacker could craft `/login?error=<script...>` or arbitrary text in the URL. The template must render **a server-controlled fixed string** to avoid XSS and exception leakage.

Because `?error` can be visited directly in a browser, the UI showing "sign in failed" for this flag **is not proof that an actual login attempt just happened**. All auditing, lockout, and rate limiting must rely on server-side authentication events, never on views of `GET /login?error`.

### 5.2. Messages You Must Not Display

Never output:

~~~text
"User linh not found"
"User linh exists, but password is incorrect"
"Account is locked until 15:30"
"This email is already registered and unverified"
"SQL timeout on table account_credentials"
"BadCredentialsException: ..."
~~~

These either leak account existence/status or expose infrastructure details. Only after users prove ownership via recovery/MFA or a trusted session can the system offer **targeted guidance**, never on the public unauthenticated login screen.

### 5.3. Safe Yet Helpful Messaging

A suggested wording:

> Unable to sign in with the provided credentials. Please check your details and try again, or use account recovery.

It does not confirm the account exists, does not claim specifically that the password was wrong, and offers the next action. Avoid writing "this username does not exist, please register" prior to ownership verification. Support or service-unavailable retry messages should also maintain safe disclosure levels.

## 6. Hiding Account Existence at Both the Provider Layer and UI Layer

Having a handler block exception messages is **necessary but not sufficient**. You must audit everything from database lookup to external response.

### 6.1. DaoAuthenticationProvider and UsernameNotFoundException

`AbstractUserDetailsAuthenticationProvider` defaults `hideUserNotFoundExceptions` to **`true`**. In the default flow, both nonexistent accounts and wrong passwords typically translate into **`BadCredentialsException`** at the authentication provider layer.

~~~java
// DO NOT disable this flag just to show "username not found":
provider.setHideUserNotFoundExceptions(false);
~~~

This is an **anti-example**, not advice. Setting `false` lets `UsernameNotFoundException` propagate to callers, increasing the risk of distinguishing existing vs. absent accounts if upper layers handle them differently.

You must still test against your real provider/custom `UserDetailsService`: a custom handler or controller can still leak accounts even when the default provider masks the exception name.

### 6.2. Three Scenarios That Should Share Equivalent Public Outcomes

| Internal scenario | What users should see on public form login | What operations can record |
|---|---|---|
| Username does not exist | A generic failure message | Login failure event, safely classified reason code |
| Username exists, wrong password | **Same message**, same URL/status pattern | Bad credentials, rate-limit signals |
| Username exists, disabled/locked | **Do not confirm account status** | Account-state reason, compliance/security event |

Some products want specialized UX for "locked accounts". Even when risk tolerance allows it, **unauthenticated responses** should not confirm account status; provide generic guidance toward recovery. A secondary identity-verification/recovery step is where targeted instructions belong per policy.

### 6.3. Do Not Vary Redirects or Status Codes

A generic body helps little if responses differ like this:

~~~text
unknown user  -> HTTP 404
wrong pass    -> HTTP 401
locked user   -> HTTP 423

or

unknown user  -> /register?user=linh
wrong pass    -> /login?retry
locked user   -> /support/locked-account
~~~

Attackers can still distinguish cases by status, URL, response headers, cookies, or HTML length. For browser form login, a **common `failureUrl`** reduces discrepancy factors. For 401 APIs, verify uniform body, status, and endpoint behavior across all failure cases.

Do not return `200 OK` for every failure and call it secure: a 200 response with differing content, timing, or cookies still leaks information. Status codes should match the protocol while remaining consistent across cases you intend to conceal.

### 6.4. Timing Side-Channels

Suppose a lookup returns immediately when a user is not found, while existing users run an expensive bcrypt hash check. Even with identical URLs and bodies, attackers can collect samples and measure latency differences.

Control **early exits**, verification time, dummy password checks, caching, rate limiting, and load variance. Spring Security includes mitigations to reduce timing gaps in the default provider flow, yet **cannot promise strictly uniform timing**: custom providers, databases, tenant lookups, slow hashes, and lockout policies can still create distinguishable side channels.

Do not insert `Thread.sleep(500)` on every failure as a "complete fix": it invites DoS, leaves other latency sources untouched, and still produces measurable statistical distributions. Test statistically under realistic load and combine with brute-force/credential-stuffing defenses.

## 7. Custom failureHandler for Browsers and JSON Clients

### 7.1. Fixed Redirect Without Saving Exception to Session

A browser app may prefer handling redirects directly rather than relying on `SimpleUrlAuthenticationFailureHandler`:

~~~java
@Bean
AuthenticationFailureHandler safeBrowserFailureHandler() {
    return (request, response, exception) -> {
        // Do not include exception.getMessage() in the URL or body.
        response.sendRedirect(
                request.getContextPath() + "/login?error");
    };
}
~~~

This is a **bean config snippet**, not a standalone program. It skips `saveException`, so it does not create a session just to hold `AuthenticationException`. If a session already existed from an earlier attempt, clear any stale error attribute if needed. Note that it does not replace the authentication filter's session/security lifecycle.

The redirect target is hardcoded server-side, never taken arbitrarily from client input. If using `next`/`returnUrl` queries, enforce strict validation and open-redirect checks.

Wiring it:

~~~java
http.formLogin(form -> form
    .loginPage("/login")
    .failureHandler(safeBrowserFailureHandler())
    .permitAll());
~~~

This is a configuration snippet; use only one handler policy. If you choose a custom `failureHandler`, do not add `failureUrl` elsewhere expecting both to stack.

### 7.2. Returning 401 JSON for AJAX Login

If the client submits forms via JavaScript/fetch and expects an API response:

~~~java
@Bean
AuthenticationFailureHandler safeJsonFailureHandler() {
    return (request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");

        response.getWriter().write(
            "{\"error\":\"Unable to sign in with the provided credentials.\"}");
    };
}
~~~

This is a Spring bean snippet. It **never returns exception details** and produces the exact same response across concealed authentication errors. If using request/response wrappers or standard JSON schemas, use a proper JSON serializer rather than string concatenation with dynamic inputs.

For **same-origin SPAs using session cookies**, state-changing requests—including login endpoints per policy—still require CSRF protection. CORS does not replace CSRF, and a 401 failure handler does not automatically convert 403 CSRF errors into 401.

### 7.3. Should You Choose Redirect or JSON?

| Client | Sensible response style | What to test |
|---|---|---|
| Browser submitting traditional HTML form | Redirect `/login?error`, then GET login page | Hidden CSRF input, fixed error flag, URL leaks no account |
| Client using fetch/XHR | `401` JSON with fixed schema | Content type/encoding, credentials/cookies, no unexpected HTML redirect |
| Mobile app using dedicated API | JSON/status per contract | Authentication mechanism may not be form login |
| Bearer JWT API resource server | Typically uses bearer entry point, **not formLogin failureHandler** | `WWW-Authenticate`, token errors, detail protection |
| IdP/OIDC login | OAuth2 failure handler/entry point per flow | State/nonce/callback, do not confuse with form-login credentials |

Do not enable both form login and bearer auth on the same URL/chain without clear boundaries. Different failures traverse **different filters/handlers**; `formLogin().failureHandler(...)` does not govern every authentication failure across the whole application.

## 8. Runnable Java 17 Example: Two Failure Handlers, Multiple Exceptions, One Message

The example below **does not require a Servlet container or Spring Boot**. It uses Spring Security's real `SimpleUrlAuthenticationFailureHandler` and `AuthenticationFailureHandler`, plus `MockHttpServletRequest`/`MockHttpServletResponse` from Spring Test to inspect responses.

We simulate:

1. A browser handler redirecting to `/login?error` on wrong password, nonexistent account, or disabled account.
2. The default handler with a fixed `failureUrl` storing `AuthenticationException` in the session (for view access), even though **the public URL reveals no cause**.
3. A custom JSON handler returning `401` with a fixed body without leaking exceptions to clients.
4. Console labels printed **solely for learning**; these labels are never sent to end users.

### 8.1. Project Structure

~~~text
login-failure-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/LoginFailureDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'login-failure-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.LoginFailureDemo'
}
~~~

The example pins Spring Security 6.3.8/Spring Framework 6.1.18 so the article's APIs are reproducible. **Do not treat pinned example versions as current production recommendations**: follow the Spring Boot BOM/supported lines and apply security patches.

### 8.2. Complete Java Code

Create `src/main/java/example/LoginFailureDemo.java`:

~~~java
package example;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.WebAttributes;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

public final class LoginFailureDemo {

    private static void browserAttempt(
            String caseName, AuthenticationException failure)
            throws IOException, ServletException {

        SimpleUrlAuthenticationFailureHandler handler =
                new SimpleUrlAuthenticationFailureHandler(
                        "/login?error");

        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        handler.onAuthenticationFailure(request, response, failure);

        System.out.println(caseName + " redirect -> "
                + response.getRedirectedUrl());

        boolean exceptionCached =
                request.getSession(false) != null
                && request.getSession(false).getAttribute(
                        WebAttributes.AUTHENTICATION_EXCEPTION) != null;

        System.out.println(caseName + " session exception -> "
                + exceptionCached);
    }

    public static void main(String[] args) throws Exception {
        // Same public URL for three internal failure reasons.
        browserAttempt(
                "bad password",
                new BadCredentialsException("wrong password"));
        browserAttempt(
                "unknown account",
                new UsernameNotFoundException("unknown username"));
        browserAttempt(
                "disabled account",
                new DisabledException("account disabled"));

        // Dedicated JSON response without leaking exception type.
        AuthenticationFailureHandler genericJson =
                (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"error\":\"Sign in failed\"}");
        };

        MockHttpServletRequest jsonRequest =
                new MockHttpServletRequest("POST", "/login");
        MockHttpServletResponse jsonResponse =
                new MockHttpServletResponse();

        genericJson.onAuthenticationFailure(
                jsonRequest, jsonResponse,
                new UsernameNotFoundException("user absent"));

        System.out.println("json status -> "
                + jsonResponse.getStatus());
        System.out.println("json content type -> "
                + jsonResponse.getContentType());
        System.out.println("json body -> "
                + jsonResponse.getContentAsString());
    }
}
~~~

### 8.3. Running and Stdout

If the project has a compatible Gradle Wrapper:

~~~bash
./gradlew run
~~~

If using a preinstalled Gradle, run `gradle run`; on Windows PowerShell with wrapper, use `.\gradlew.bat run`.

Lines printed by `System.out.println` (excluding Gradle logs):

~~~text
bad password redirect -> /login?error
bad password session exception -> true
unknown account redirect -> /login?error
unknown account session exception -> true
disabled account redirect -> /login?error
disabled account session exception -> true
json status -> 401
json content type -> application/json;charset=UTF-8
json body -> {"error":"Sign in failed"}
~~~

### 8.4. Explaining the Output

- All three `onAuthenticationFailure` calls with three different exception subclasses share **one fixed `defaultFailureUrl`**, so `getRedirectedUrl()` matches across all of them. The console prints `caseName` solely **for demo clarity**; browsers only receive the generic URL.
- `SimpleUrlAuthenticationFailureHandler` with redirects and session creation allowed by default stores the exception under `WebAttributes.AUTHENTICATION_EXCEPTION`. That is why the `session exception` lines print `true`—and why templates must never render the exception message directly.
- The custom JSON handler receives `UsernameNotFoundException` yet **never reads it when building the body**, so status 401 and the message stay generic. Passing `BadCredentialsException` or `DisabledException` to the same handler yields the exact same fixed body.
- There is no password hashing, `AuthenticationManager`, provider, or account database in this demo. It **simulates failure handling after the filter identifies an error**; it does not verify the security of a complete login flow.

**Note:** example outputs are based on the pinned library APIs/behavior; actual bodies/statuses through a real Servlet container also depend on the filter chain, proxies, other failure handlers, and exception mapping. To verify a full system, write integration tests with real form login.

## 9. Full Spring Boot Integration: Choosing One Failure Policy

### 9.1. Browser Form Login Configuration

~~~java
@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/forgot-password", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .failureUrl("/login?error")
                .permitAll());
        return http.build();
    }
}
~~~

This is a **code fragment inside a Spring Boot Servlet app**, not standalone compilable. It needs `@Configuration`/`@Bean`, imports, `UserDetailsService`/provider, and a GET `/login` controller/template. `/forgot-password` is an anticipated route; implement its recovery controller or remove the link from the UI.

### 9.2. A Separate SecurityFilterChain for AJAX Login

If the app needs JSON-style login, define an explicit boundary:

~~~java
@Bean
SecurityFilterChain apiLoginSecurity(
        HttpSecurity http,
        AuthenticationFailureHandler safeJsonFailureHandler)
        throws Exception {

    http
        .securityMatcher("/api/login/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll())
        .formLogin(form -> form
            .loginProcessingUrl("/api/login/session")
            .failureHandler(safeJsonFailureHandler));

    return http.build();
}
~~~

This snippet **only demonstrates attaching a failure handler to a chain**; it does not address JSON request bodies, CSRF strategy, session policy, or `@Order` across multiple chains. `UsernamePasswordAuthenticationFilter` reads **form parameters** by default and does not parse arbitrary JSON payloads; JSON input requires an appropriate authentication converter/filter. Do not copy this as a "complete JSON login" without implementing credential extraction.

**Warning:** if the app has both a fallback Web chain and a narrow API chain, configure `@Order` properly and verify `POST /api/login/session` hits the API chain—otherwise the API failure handler may never execute.

### 9.3. Pick One Clear Handler

Within a single chain, choose **one** of:

~~~java
form.failureUrl("/login?error");
~~~

or:

~~~java
form.failureHandler(safeBrowserFailureHandler);
~~~

or:

~~~java
form.failureHandler(safeJsonFailureHandler);
~~~

These three are **alternatives**, not sequential chained calls. When a generic message and redirect back to the login page meet your needs, `failureUrl` is usually sufficient. Write a custom handler when a specific response policy adds clear value.

## 10. How Does AuthenticationFailureHandler Differ from Other Error Handlers?

Not every HTTP security error passes through `formLogin().failureHandler`.

| Mechanism / error | Component that may handle it | Why it differs from form login failure |
|---|---|---|
| `POST /login` wrong credentials | `UsernamePasswordAuthenticationFilter` → `AuthenticationFailureHandler` | Exact scope of form-login failure |
| `GET /private` unauthenticated | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Request to a protected URL, not a failed login attempt |
| Logged-in principal missing role | `AccessDeniedHandler` | Authorization failure, not bad credentials |
| `POST /login` missing CSRF | `CsrfFilter` / access denied handling | Can be blocked before the auth filter |
| Wrong HTTP Basic | `BasicAuthenticationFilter` / Basic auth entry point | Different auth mechanism with protocol challenge |
| Invalid/expired Bearer token | `BearerTokenAuthenticationFilter` / Bearer entry point | Follows OAuth2 Bearer protocol |
| OIDC/OAuth2 login callback failed | OAuth2 authentication filter failure handler | Different filter/protocol from username/password forms |
| Spring MVC controller throws exception | `@ControllerAdvice` / Spring MVC error handling | Does not route to formLogin failureHandler |
| DB outage / JWK service outage | Infrastructure/provider and specific exception mapping | Must fail closed and alert; never mask operational outages |

Do not blindly apply `ExceptionMappingAuthenticationFailureHandler` to redirect distinct account states to different pages, as `DisabledException`/`LockedException` can create discrepancy factors. If custom recovery UX is needed, verify identity before disclosing details.

### 10.1. Do Not Confuse 401 and 403

- **401 Unauthorized** (a slightly misleading HTTP name): typically means authentication is missing or just failed, optionally with a challenge.
- **403 Forbidden**: usually means access was denied by authorization or blocked by a protection filter like CSRF; also depends on filter/entry-point configuration.
- **302 redirect** to login page: common pattern for HTML browser flows.

A status code alone does not tell you whether the password was wrong, an account exists, or authorization failed; inspect the actual **filter/exception source**. For anti-enumeration UIs, compare **status, redirects, bodies, headers, and timing** across all account scenarios.

## 11. Preventing Account Enumeration Across the Entire User Journey

A login page with a generic message can still leak accounts on neighboring endpoints:

### 11.1. Registration and Forgot Password

Suppose an application returns:

~~~text
POST /register: "Email already exists"
POST /forgot: "Account not found"
POST /login: "Sign in failed"
~~~

An attacker simply calls `/forgot` instead of `/login` to enumerate accounts. Maintain a consistent disclosure policy per threat model across **login, reset, registration, recovery, and MFA enrollment**, while keeping UX smooth for legitimate users through verified channels.

For reset requests, a generic notice like "If a matching account exists, we will send instructions" is standard practice. You must also guard response timing, rate limits, email/notification side effects, and protect reset tokens from disclosure.

### 11.2. Rate Limiting Must Not Become a Leak Source

If real accounts are publicly locked after N bad attempts while nonexistent accounts get a different message, lockout becomes an account-existence oracle. Keep public messages generic while enforcing internal throttle/risk-scoring thresholds across normalized usernames, networks/IPs, and device/rate windows.

Be careful not to lock purely by IP (which impacts shared NAT/mobile users), and avoid permanently locking accounts based solely on attacker-supplied usernames (enabling DoS). Rate limiting is a **supplementary defense**, not a replacement for password hashing, MFA, and monitoring.

### 11.3. MFA and Sensitive Account States

A prompt like "Password accepted, now complete MFA" should only appear **after the password step has been validly verified** within a protected flow. Never confirm which accounts have MFA at a username-only step without security justification. Avoid logging challenges/tokens or putting secrets into redirects.

### 11.4. Timing Is Hard to Control Completely

Public response comparisons should include:

- Nonexistent username.
- Existing username, wrong password.
- Existing username, disabled/locked.
- Cache hit vs. miss.
- Slow or unavailable DB.
- Different password hash speeds by cost/algorithm.
- Rate limiting and async email/notification triggers.

Aim to reduce statistically significant distinguishability and enumeration throughput; do not set unrealistic targets like "every request must take exactly 200 ms". Layer defenses and measure under near-production load.

## 12. Logging, Auditing, and Sensitive Data

### 12.1. What Should Operations Log?

Emit structured audit events such as:

~~~json
{
  "event": "AUTH_LOGIN_FAILURE",
  "requestId": "opaque-correlation-id",
  "authMethod": "form",
  "result": "DENIED",
  "reasonCode": "BAD_CREDENTIALS_GENERIC",
  "clientBucket": "rate-limiter-key-redacted"
}
~~~

This is an **example schema**, not output from a specific app. If operations need `ACCOUNT_DISABLED` or `SERVICE_UNAVAILABLE` classifications for alerting, route them strictly to **protected internal channels** with restricted retention/access and bounded label cardinality. You do not always have to log verbatim usernames/emails, and never log raw client-supplied usernames without sanitization.

**Never log:** raw passwords, `Authorization` headers, session cookies, CSRF tokens, reset tokens, bearer JWTs, encoded password hashes, raw `AuthenticationException` messages that might contain sensitive data, or unredacted `Authentication` objects.

### 12.2. Should Exceptions Be Sent to Metrics?

Avoid using `exception.getMessage()` as a metric label: strings vary unpredictably, can contain internal data, and cause high cardinality. Use **allowlisted enum reason codes** such as `AUTH_BAD_CREDENTIALS`, `AUTH_ACCOUNT_STATE`, and `AUTH_INFRASTRUCTURE_ERROR`.

Telemetry should expose login failure rates, password-spraying spikes, `AuthenticationServiceException` error rates, latency, and recovery requests—without turning into an identity-enumeration tool for unauthorized viewers.

### 12.3. Relationship to HttpSession

If a redirect handler saves the exception in the session, that data has a lifecycle distinct from `SecurityContext`, remember-me, and CSRF tokens. Never output `WebAttributes.AUTHENTICATION_EXCEPTION.message` on a public page, even with encrypted sessions or `HttpOnly` cookies. Even though users cannot read server-side session storage directly, **your application template can still leak it**.

## 13. Functional and Security Testing Matrix

| Scenario | Public behavior to verify | Internal check |
|---|---|---|
| Wrong password for real account | `/login?error`, generic message | Provider/encoder rejects properly |
| Nonexistent username | **Same redirect/body/status** | `UsernameNotFoundException` not leaked |
| Account disabled | **Does not disclose status** | Account state logged safely |
| Account locked | Generic public behavior | Lockout/rate limiting opens no enumeration |
| Account expired | Generic message | Dedicated recovery policy |
| Password expired | Not disclosed prior to required verification | Secure password-change flow |
| DB outage / infra failure | No stacktrace, no accidental login | Clear operational error/alert |
| `GET /login` without error flag | Renders form normally | Does not record a login failure event |
| `GET /login?error` visited directly | Fixed message, ignores query value | Not treated as a login attempt |
| `GET /login?error=USER_NOT_FOUND` | Still fixed message | Never parses reason from client |
| POST missing CSRF | Login rejected | CSRF filter runs before failure handler if configured |
| POST valid CSRF, wrong credentials | Form failure handler runs | Proper session/exception handling |
| GET error page on mobile/JS | No redirect loop | Client handles HTTP cleanly |
| Browser redirect mode | Identical Location URL across error types | No username/exception in query |
| JSON handler mode | Identical `401` body/schema | Proper Content-Type/UTF-8 |
| No FailureUrl set | Exception message not exposed publicly by default | Check SimpleUrl default response |
| Redirect handler with session | Does not render `AUTHENTICATION_EXCEPTION` | Session attribute managed properly |
| Multiple `SecurityFilterChain`s | POST `/login` hits right chain | `@Order` and matchers align |
| Custom form parameter names | Filter reads right username/password | Mismatch not misdiagnosed as missing account |
| Lost CSRF/session cookie | Reasonable UI guidance | Secure/SameSite/Path/proxy cookie config |
| Valid login | Skips failure handler | Authentication stored in context after verify |
| Enumeration probing | Indistinguishable status/body/redirect | Timing/rate limits/headers measured |
| Forgot password / registration | No account leak on adjacent endpoints | Consistent disclosure policy |
| Open redirect probe via returnUrl | Never redirects to attacker domain | URL restricted to allowlist/safe relative paths |
| BadCredentialsException with sensitive message | Raw message never emitted | Logs/metrics redacted |
| Repeated retries / credential stuffing | No unbounded brute force | Rate limiting, detection, MFA |
| Real proxy / container tests | Public behavior matches local | Headers/redirect paths match context |
| ERROR/ASYNC dispatches | Handler not re-invoked unexpectedly | Proper dispatcher/filter lifecycle |

### 13.1. Illustrative MockMvc Integration Tests

In a Spring Boot project with `spring-security-test`, you can test:

~~~java
mockMvc.perform(post("/login")
        .with(csrf())
        .param("username", "known-user")
        .param("password", "wrong-password"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?error"));
~~~

This is a **test snippet**, not standalone compilable. You need a valid-account/wrong-password fixture, `MockMvcRequestBuilders.post`, `SecurityMockMvcRequestPostProcessors.csrf`, status/redirect matchers, and the app security chain.

Add a second test with a nonexistent username and verify the exact same redirect; add disabled/locked account tests if policy calls for them. For custom JSON handlers, assert status 401 and the fixed body. To detect timing leaks, run statistically controlled multi-request tests/instrumentation rather than trying to prove safety with a single `System.nanoTime()` call.

### 13.2. Verify Responses from the Browser's Perspective

Integration tests must check **what the client observes**, not merely that a handler method ran:

- HTTP status and `Location` header.
- HTML form has a valid CSRF token, and the password field is never prefilled with secrets.
- Only one fixed message appears, with no embedded exception text.
- JSON `Content-Type` and character encoding.
- Cache headers when displaying sensitive info.
- No username, password, or exception in query strings, cookies, redirects, or response bodies.
- Controls for brute force, credential stuffing, and monitoring.

Specifically, `MockMvc` does not fully replace HTTP testing through real proxies, servlet containers, reverse-proxy URL rewriting, and real cookie security attributes.

## 14. Common Implementation Mistakes

**Mistake 1 — Displaying `exception.getMessage()` verbatim.**  
Can expose existing usernames, account status, and infrastructure details. Render a fixed message instead.

**Mistake 2 — Redirecting differently per `AuthenticationException`.**  
Attackers distinguish `UsernameNotFoundException`, `LockedException`, and `BadCredentialsException` via `Location`. Use a single public outcome or a verified recovery flow.

**Mistake 3 — Assuming `failureUrl` and `failureHandler` stack together.**  
`failureUrl` is a handler shortcut; pick one clear response policy and test the final configuration.

**Mistake 4 — Setting `failureUrl` without a `GET /login` endpoint.**  
Browsers hit 404 or custom errors. Provide a controller/template and `permitAll`.

**Mistake 5 — `POST /login` falls outside `securityMatcher`.**  
The authentication filter ignores the POST. Check the selected chain and login processing URL.

**Mistake 6 — Disabling CSRF because login POST returns 403.**  
That is typically CSRF protection doing its job, not the password provider failing. Fix the form token.

**Mistake 7 — Returning 200 with differing HTML per account state.**  
Matching status codes do not mask differences in body, length, cookies, or timing.

**Mistake 8 — Returning unexpected HTML redirects to AJAX API clients.**  
Clients fail to parse it and can loop. Use a dedicated 401 JSON handler when the API contract expects JSON.

**Mistake 9 — Exposing `exception.getClass().getSimpleName()` as a public reason.**  
Even without a message, the exception class name still leaks account state.

**Mistake 10 — Setting `setHideUserNotFoundExceptions(false)` for "better UX".**  
Increases account distinguishability, especially if upper handlers/controllers alter responses.

**Mistake 11 — Ignoring timing side-channels.**  
Returning early when a user is absent can leak accounts despite generic messages. Design providers, KDFs, rate limits, and tests carefully.

**Mistake 12 — Treating `/login?error` views as audit evidence.**  
Anyone can load that URL directly; failure events must originate from server-side authentication attempts.

**Mistake 13 — Logging raw credentials on authentication failures.**  
A log leak can lead to account takeover. Log only minimized, redacted data.

**Mistake 14 — Having a custom failure handler create an authenticated token to "keep the user".**  
Failed authentication must never produce a trusted session. Handlers only craft safe responses and audits.

**Mistake 15 — Introducing open redirects in `failureHandler`.**  
Never trust client-supplied `returnUrl`/`next`; use fixed targets or an allowlist of relative URLs.

**Mistake 16 — Assuming `formLogin().failureHandler` handles Basic/JWT/OIDC failures.**  
Each mechanism has its own filters/entry points/handlers; test each separately.

**Mistake 17 — Neglecting session exceptions after redirects.**  
`SimpleUrlAuthenticationFailureHandler` normally saves exceptions for views; never render or retain unnecessary sensitive data.

**Mistake 18 — Suggesting "create a new account" on every failed login.**  
If the username actually exists and the user mistyped their password, that advice is both wrong and risks confirming accounts. Offer generic advice to check credentials or use recovery.

## 15. Review Questions and Production Checklist

### 15.1. Self-Check Questions

**Q1.** Is `failureUrl("/login?error")` the code that verifies passwords?  
**Answer:** No. It configures the response after the authentication filter/provider reports failure.

**Q2.** Can `failureHandler` return 401 JSON instead of redirecting?  
**Answer:** Yes. It controls the `HttpServletResponse` on authentication failure; avoid leaking exception details.

**Q3.** Should nonexistent accounts and wrong passwords redirect to two different URLs?  
**Answer:** Not on a public login screen defending against account enumeration; a unified public outcome is safer.

**Q4.** Can `SimpleUrlAuthenticationFailureHandler` store exceptions in the session?  
**Answer:** Yes, when redirecting/forwarding per configuration; redirects usually save into the session if present or allowed. Views must never expose those details publicly.

**Q5.** Does `POST /login` without CSRF necessarily invoke the failure handler?  
**Answer:** No. `CsrfFilter` can block the request before the form login filter runs, typically returning 403.

**Q6.** What is `hideUserNotFoundExceptions` enabled by default for in DAO providers?  
**Answer:** It avoids distinguishing unknown usernames from wrong passwords via the default exception type; it does not eliminate all side channels.

**Q7.** Can enumeration be prevented purely with a generic HTML message?  
**Answer:** No. Check status codes, URLs, headers, cookies, response length, timing, registration/reset flows, and rate limits.

**Q8.** If a user sees `/login?error`, does that prove they just entered a wrong password?  
**Answer:** No. The `error` query flag can be typed manually in the URL, and internal failures are not always wrong passwords.

**Q9.** Does the form login handler catch JWT signature errors?  
**Answer:** Not by default. Bearer tokens are handled by resource-server filters and their own entry points.

**Q10.** Should a custom handler log username and raw password for debugging?  
**Answer:** No. Log only controlled security events and never log credential secrets.

### 15.2. Implementation Checklist

- [ ] `UsernamePasswordAuthenticationFilter` intercepts `POST loginProcessingUrl` in the right `SecurityFilterChain`.
- [ ] Authentication is decided by `AuthenticationManager`/providers, never building trusted principals from raw input.
- [ ] GET login page and POST login processing URL have proper mappings/`permitAll`.
- [ ] Pick **one** failure handling mode: `failureUrl` or custom `failureHandler` per client contract.
- [ ] Login page uses a **fixed** message; never renders `AuthenticationException.message` or query values as message text.
- [ ] Unknown username, wrong password, and disabled/locked accounts have indistinguishable public outcomes.
- [ ] Verify status, redirect URL, headers, cookies, body, length, and timing.
- [ ] `DaoAuthenticationProvider` does not unnecessarily expose `UsernameNotFoundException`.
- [ ] Maintain CSRF protection for browser login; do not conflate CSRF failures with auth failures unconditionally.
- [ ] For AJAX, return consistent JSON status/schema; avoid unintended HTML redirects.
- [ ] Never use client-supplied URLs or exception details for open redirects or unsanitized logs.
- [ ] Enforce rate limiting, credential-stuffing detection, MFA where appropriate, and secure password hashing.
- [ ] Apply consistent anti-enumeration policies to reset, registration, and recovery endpoints.
- [ ] Manage `WebAttributes.AUTHENTICATION_EXCEPTION` in sessions and never display it publicly.
- [ ] Monitor real errors via access-controlled internal metrics/audits, never leaking account reasons publicly.
- [ ] Write MockMvc/integration/E2E tests against the real provider and security chain, including unknown/disabled users.
- [ ] Verify infrastructure failures never turn into "successful login" or public stacktraces.
- [ ] When upgrading Spring Security versions, check Javadoc for `AbstractAuthenticationFilterConfigurer` and `SimpleUrlAuthenticationFailureHandler`.

**Remember:** `failureUrl` and `AuthenticationFailureHandler` govern **how to respond when authentication fails**, not whether an account exists or a password matches. UIs must display generic messages without exposing `AuthenticationException`, while providers, timing, rate limits, recovery flows, and all other HTTP responses must uphold the boundary against **account enumeration**.

### Official References

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): login page, form POST, CSRF token, and the `error` parameter.
- [Spring Security — AbstractAuthenticationFilterConfigurer JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): `failureUrl`, `failureHandler`, and default redirects.
- [Spring Security — SimpleUrlAuthenticationFailureHandler JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html): redirect/forward, status when URL is absent, and `saveException`.
- [Spring Security — AuthenticationFailureHandler JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): `onAuthenticationFailure`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `hideUserNotFoundExceptions`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): provider, `UserDetailsService`, and `PasswordEncoder`.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication error messages, discrepancy factors, and timing.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): account enumeration and secure password resets.
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): rate limiting, threat signals, and defenses.
