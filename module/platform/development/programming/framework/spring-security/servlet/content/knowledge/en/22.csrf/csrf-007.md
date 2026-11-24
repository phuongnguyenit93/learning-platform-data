# CSRF in Login, Logout, and State-Changing Forms — Spring Security Servlet

## 1. What Is CSRF and Why Do Forms Need Protection?

**Cross-Site Request Forgery (CSRF)** is a situation where an attacker-controlled page causes a user's browser to send a request to another application while the browser automatically attaches credentials, such as the `JSESSIONID` session cookie. The server sees a valid session yet **cannot infer that the user truly intended to perform the operation** solely from the cookie.

For example: a user is logged into `https://app.example.test`. They open another page containing a form that sends a POST to the application's `/profile`. Depending on cookie policy, page context, and browser, the authentication cookie may be automatically sent with the request. If the application checks only the cookie without verifying the legitimate origin of the operation, data can be modified against the user's intent.

Three conditions typically create CSRF risk:

1. An endpoint with side effects: login, logout, update, deletion, or business execution.
2. The browser can automatically attach credentials for the target without the attacking page's code knowing the credential values.
3. The backend lacks a verification step for a signal that a malicious page from another origin cannot easily know or forge.

A **CSRF token** is that signal: the server generates an unpredictable value for legitimate pages; the form or JavaScript sends it back in a parameter or header; the backend verifies it before executing the action. A page from another origin normally cannot read the token in the application's HTML due to the same-origin policy.

This lesson uses **Spring Security Servlet + Spring MVC + session-based authentication**. Spring Security WebFlux/reactive uses different components and APIs.

## 2. Three Critical Flows: Login, Logout, Data Modification

| Flow | UI / endpoint | Risk without CSRF | Required behavior |
| --- | --- | --- | --- |
| Login | `GET /login`, `POST /login` | **Login CSRF**: forcing the user to use a session logged into the attacker's account | GET can be public, but login POST must include a token |
| Logout | `POST /logout` | **Logout CSRF**: external page triggers unintended logout | Log out via a POST form with a token, do not perform logout via a GET link |
| Data update | `POST /profile`, `PUT`, `PATCH`, `DELETE` | Unintended updates/deletions/transactions | Check token on write operations; continue authentication, authorization, and data validation |

### 2.1. Why Does Login Also Need CSRF When the User Is Unauthenticated?

In **login CSRF**, an attacker tries to make the victim's browser log in using *an account controlled by the attacker*. The victim might think they are using their personal account and then save information or perform activities in an account the adversary can observe.

`permitAll()` in `authorizeHttpRequests` only permits accessing an endpoint without logging in beforehand. It **does not disable the CSRF filter**. Therefore, the login form must still carry a token, even though `GET /login` is a public page.

Standard flow:

1. Browser loads `GET /login` and receives HTML with a CSRF token.
2. User enters `username` and `password`.
3. Form submits `POST /login` with the current session cookie and hidden CSRF token.
4. Spring Security verifies CSRF before authenticating the account.
5. Only with a valid token does the authentication flow check credentials and handle success/failure.

### 2.2. Why Should Logout Be POST?

Logging out changes authentication state. A link like `<a href="/logout">Log out</a>` issues a GET, easily triggered via navigation or automatic page prefetchers. With CSRF enabled, Spring Security by default requires a POST containing a valid token for logout. `GET /logout` is not the logout action; depending on configuration it may display a confirmation page.

After logout, the old session and token should no longer be reused. A fresh login page can issue a new token for the next session.

### 2.3. CSRF Does Not Replace Authorization

A `POST /orders/123/cancel` request with a valid CSRF token must still verify whether the caller has permission to cancel order `123`. CSRF prevents one class of request forgery; it does not address data ownership, XSS, injection, or validation.

## 3. Default Mechanism in Spring Security 6 Servlet

In Spring Security configuration for Servlet:

1. `CsrfFilter` determines whether the request requires verification. By default `GET`, `HEAD`, `TRACE`, and `OPTIONS` are excluded from verification; `POST`, `PUT`, `PATCH`, `DELETE`, and other methods must carry a token.
2. `CsrfTokenRepository` manages the expected token. The default for this kind of configuration is `HttpSessionCsrfTokenRepository`, binding the token to the HTTP session. Token generation/loading can be performed lazily (deferred).
3. When rendering a Spring MVC view, the request can have a `_csrf` attribute providing `parameterName`, `headerName`, and `token`.
4. Forms submit the hidden field back; AJAX sends the corresponding header. `CsrfFilter` retrieves the received value and compares it against the expected token. Missing or wrong tokens typically return **HTTP 403 Forbidden**, before the controller is invoked.
5. After successful authentication or logout, integrated Spring Security strategies clear the old token; the next request must obtain a new token. SPAs holding onto old tokens may encounter 403 after login/logout.

The default parameter name is typically `_csrf` and header is typically `X-CSRF-TOKEN`; retrieve the actual names from `_csrf` because repository and request handler configurations may differ.

**Spring Security 6 uses an XOR CSRF request handler to mask the token value when rendered to pages**, mitigating risks such as BREACH. Consequently, the token value seen across two renders may differ even though the raw token in the repository has not changed. Do not compare displayed tokens to conclude the session changed.

## 4. Runnable Demo: Spring Boot MVC + Thymeleaf

Create a Spring Boot 3.x project using **Java 17+** with dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`, and `spring-boot-starter-thymeleaf`. To run the tests in section 7, add `spring-boot-starter-test` and `spring-security-test` to test dependencies. Place the files in this structure:

```text
src/main/java/com/example/csrf/
  CsrfFormsApplication.java
  SecurityConfig.java
  FormController.java
src/main/resources/templates/
  login.html
  home.html
src/test/java/com/example/csrf/
  CsrfFormsSecurityTests.java
```

### 4.1. Startup Class

**`CsrfFormsApplication.java`**

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormsApplication.class, args);
    }
}
```

### 4.2. SecurityFilterChain Configuration

**`SecurityConfig.java`**

```java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error", "/css/**").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        return http.build();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

`csrf(Customizer.withDefaults())` explicitly states CSRF is enabled; in standard Spring Security Servlet configuration, CSRF is already enabled by default. `requestMatchers("/login").permitAll()` does not exempt POST from CSRF tokens. Spring Security handles `POST /login` and `POST /logout` via its own filters; there is no need to write controllers to handle those two POSTs.

The `learner` / `demo-password` credentials are only for local learning/demo, not safe sample passwords for Internet deployment.

### 4.3. Data-Updating Controller

**`FormController.java`**

```java
package com.example.csrf;

import java.security.Principal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class FormController {
    private final ConcurrentMap<String, String> displayNames =
        new ConcurrentHashMap<>();

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/")
    String home(Principal principal, Model model) {
        String username = principal.getName();
        model.addAttribute("username", username);
        model.addAttribute(
            "displayName",
            displayNames.getOrDefault(username, username)
        );
        return "home";
    }

    @PostMapping("/profile")
    String updateProfile(
            @RequestParam("displayName") String displayName,
            Principal principal) {
        displayNames.put(principal.getName(), displayName);
        return "redirect:/";
    }
}
```

`GET /login` renders a public form; `GET /` requires authentication; `POST /profile` actually updates demo data if the request passes both authentication and CSRF. `ConcurrentHashMap` keeps the example short and self-contained, but is not a production profile store: data is lost on restart, and the example lacks name length/validity constraints.

### 4.4. Login Form

**`src/main/resources/templates/login.html`**

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <title>Log In</title>
</head>
<body>
    <h1>Log In</h1>
    <p th:if="${param.error}">Invalid username or password.</p>
    <p th:if="${param.logout}">You have been logged out.</p>

    <form th:action="@{/login}" method="post">
        <label for="username">Username</label>
        <input id="username" name="username" required>

        <label for="password">Password</label>
        <input id="password" type="password" name="password" required>

        <button type="submit">Log In</button>
    </form>
</body>
</html>
```

With **Thymeleaf + Spring MVC + Spring Security** integration, `th:action` passes through `RequestDataValueProcessor`; Spring Security can automatically add the hidden CSRF field to POST forms. Therefore, **do not manually add a second hidden `_csrf` field** to the form above. You can inspect the rendered form DOM in the browser to confirm the CSRF field actually exists.

When the token is valid yet username/password are wrong, Spring Security runs the authentication failure branch and usually redirects back to `/login?error`. When POST lacks a token, the request is rejected at the CSRF filter before reaching password logic.

### 4.5. Data-Modifying Form and Logout

**`src/main/resources/templates/home.html`**

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <title>Profile</title>
</head>
<body>
    <h1>Profile</h1>
    <p>Account: <strong th:text="${username}"></strong></p>
    <p>Display name: <span th:text="${displayName}"></span></p>

    <form th:action="@{/profile}" method="post">
        <label for="displayName">New display name</label>
        <input id="displayName" name="displayName" required>
        <button type="submit">Save changes</button>
    </form>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Log out</button>
    </form>
</body>
</html>
```

Both forms require tokens. `POST /profile` must not be allowed to modify data merely because the cookie is valid; it must also pass CSRF verification. `POST /logout` must also carry a token for Spring Security to clear the login state. Do not turn write operations into GET just to "avoid" 403 errors.

### 4.6. Running and Self-Testing

In a Gradle Spring Boot project with Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. Open `http://localhost:8080/login`, use the demo account `learner` / `demo-password`, change the display name on the home page, then click Log out. In DevTools, inspect the POST form payloads to verify the CSRF parameter is present; the logout form must have it too.

You can test a request intentionally **missing** a token:

```bash
curl -i -X POST http://localhost:8080/login \
  -d "username=learner&password=demo-password"
```

Expected result **HTTP 403**, because the request lacks a CSRF token, not because of a wrong password. This command only proves the rejection branch; proper login via an HTTP client requires fetching the token from GET and sending the matching session cookie. On PowerShell use `curl.exe` to avoid aliases with different behavior.

## 5. Manually Putting Tokens into Forms or AJAX

### 5.1. When a Form Does Not Use th:action

If using a Thymeleaf form with a plain `action` and wanting to manage the field manually:

```html
<form action="/profile" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <input name="displayName" required>
    <button type="submit">Save</button>
</form>
```

This is an **alternative** to Spring Security auto-inserting the field via `th:action`, not a way to insert two duplicate-named tokens. For applications with a non-`/` context path, ensure the form URL is constructed with the right context path.

### 5.2. Same-Origin Fetch/AJAX

If a server-rendered page calls a POST endpoint from JavaScript, the token and header name can be exposed in two meta tags:

```html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">
```

Example calling the demo's exact `@PostMapping("/profile")` endpoint:

```javascript
async function saveDisplayName(displayName) {
    const token = document.querySelector('meta[name="_csrf"]').content;
    const headerName =
        document.querySelector('meta[name="_csrf_header"]').content;

    const response = await fetch("/profile", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            [headerName]: token,
            "Content-Type": "application/x-www-form-urlencoded"
        },
        body: new URLSearchParams({ displayName }).toString()
    });

    if (!response.ok) {
        throw new Error("Unable to update: HTTP " + response.status);
    }
}
```

`credentials: "same-origin"` preserves cookies for the same origin. The CSRF header is an **additional** requirement: cookies alone are not enough. The example uses `application/x-www-form-urlencoded` because the controller accepts `@RequestParam`; if switching to JSON, you must adjust the payload, Content-Type, and controller parameters. Old tokens kept in SPA memory may become invalid after login/logout; fetch a fresh token.

### 5.3. CookieCsrfTokenRepository for SPAs

`CookieCsrfTokenRepository` typically uses the `XSRF-TOKEN` cookie and `X-XSRF-TOKEN` header. However, with Spring Security 6, **calling only `CookieCsrfTokenRepository.withHttpOnlyFalse()` does not automatically solve every SPA case**: you must properly handle XOR/BREACH token masking, deferred token loading, and re-issuing tokens after login/logout. Request handler/token issuance configuration must match the actual Spring Security version. Do not allow JavaScript to read the CSRF cookie unless genuinely needed; any same-origin XSS can access tokens readable by JavaScript.

## 6. Common Errors and Misconceptions

| Symptom or assumption | How to understand and handle |
| --- | --- |
| Can view `GET /login` yet `POST /login` returns 403 | Confirm the form has a real token, matching session cookie, and the token was sent; `permitAll()` does not exempt CSRF |
| Static HTML form does not show `_csrf` | Static HTML does not know session tokens; must render server-side or use an active token-issuing mechanism |
| GET `/logout` link does not log out | Use a POST form with a token; do not enable GET logout just to work around the symptom |
| AJAX gets 403 right after login/logout | Old token was cleared or session changed; reload/re-issue a token matching the new session |
| Form cached and shared or token from another session | Do not accidentally cache HTML containing a session-specific token; re-render in the right context |
| Request with a valid CSRF token can modify someone else's resource | CSRF does not replace backend role, permission, and ownership checks |
| GET still updates/deletes data | Fix the API: GET must be side-effect safe, because default CSRF checks skip GET |
| CSRF header has right name yet wrong value | Check whether the request took the current session's exact token, not hardcoded or mixed across sessions |
| Globally disabling `csrf` to avoid 403 errors | Find the cause of the missing token; `csrf.disable()` is very risky for cookie-authenticated apps |
| Assuming CORS stops CSRF | CORS mainly controls response reading and JavaScript requests; browsers can still send cross-origin forms |
| Assuming `SameSite` replaces CSRF | `SameSite` reduces risk in many contexts but depends on cookie policy, same-site subdomains, and browser cookie-sending behavior; proper server policy is still required |
| API uses Bearer tokens | If JavaScript actively attaches `Authorization` and the browser does not auto-send credentials, the threat model differs. If bearer/session tokens live in auto-sent cookies, CSRF still needs evaluation |
| XSS vulnerability present | Same-origin XSS can read/send tokens; CSRF tokens do not stop XSS. Continue escaping, CSP, and input validation |

**Never put CSRF tokens in URLs** (query strings): URLs can end up in history, logs, analytics, or Referer headers. Use hidden fields for forms and headers for AJAX. In real applications, also enforce HTTPS, `Secure`/`HttpOnly` cookies when appropriate, `SameSite`, session fixation protection, and validation.

## 7. Testing with MockMvc

Add test dependencies `spring-boot-starter-test` and `spring-security-test` to the project. File **`src/test/java/com/example/csrf/CsrfFormsSecurityTests.java`**:

```java
package com.example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormsSecurityTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void updateWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/profile")
                .with(user("learner"))
                .param("displayName", "Minh"))
            .andExpect(status().isForbidden());
    }

    @Test
    void updateWithCsrfCanProceed() throws Exception {
        mockMvc.perform(post("/profile")
                .with(user("learner"))
                .with(csrf())
                .param("displayName", "Minh"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/logout")
                .with(user("learner")))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden());
    }
}
```

Run `./gradlew test` (Windows: `.\gradlew.bat test`). `with(user("learner"))` creates a mock user for testing permissions, and `with(csrf())` adds a valid token. The update test with a token expects a redirect from the controller, showing the request passed the CSRF gate; it **does not prove** validation, per-resource authorization, or production persistence is right. You can add `.with(csrf().useInvalidToken())` to confirm an invalid token returns 403.

End-to-end browser testing must also confirm the hidden token is actually rendered, login succeeds, logout runs via POST, fresh tokens are issued after login/logout, and the session cookie matches the token. Unit/integration tests using `with(csrf())` do not automatically check whether HTML includes a CSRF field.

## 8. Pre-Deployment Checklist

1. Separate safe read operations (`GET`/`HEAD`) from write operations (`POST`/`PUT`/`PATCH`/`DELETE`); never use GET to modify state.
2. With auto-sent sessions/cookies, keep Spring Security's CSRF protection; consider narrow exceptions only after clearly understanding how credentials are actually sent.
3. `GET /login` is publicly accessible yet `POST /login` still mandates a token; distinguish 403 due to CSRF from authentication failures.
4. Logout uses POST with a token; manage token lifecycle after authentication/logout.
5. With Thymeleaf, verify `th:action` and the rendered CSRF hidden field; with handwritten HTML/AJAX, pass the token in the right parameter/header and session.
6. Test all cases: missing token, wrong token, valid token, unauthenticated/authenticated user, and unauthorized user.
7. Maintain authorization, ownership checks, validation, XSS prevention, HTTPS, and cookie policies alongside CSRF.

With Spring Security Servlet and the three form types above, the consistent practical rule is: **keep CSRF enabled, include tokens on all state-changing requests, never turn data writes into GET, and verify both accept and reject branches with tests**.
