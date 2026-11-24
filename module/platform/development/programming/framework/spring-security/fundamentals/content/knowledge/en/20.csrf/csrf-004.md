# Login Forms, Logout, and Business Operations That Must Be Considered

> **Context:** Spring Security – fundamentals / **CSRF**. This lesson focuses on **Spring MVC/Servlet applications with users logging in via a browser**, using session cookies or credentials that browsers can automatically attach. Examples use **Java 17, Spring Boot 3.5.0, Spring Security 6.x, Thymeleaf, JUnit 5, and MockMvc**. Purely non-browser/non-cookie APIs and WebFlux are distinguished separately. All URLs, accounts, and amounts in examples are for learning purposes only, never for real transactions.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why **login**, **logout**, and **all business state-changing operations** fall within CSRF evaluation scope.
2. Explain how CSRF exploits browser auto-sent cookies/credentials, distinguishing **authentication**, **authorization**, and **CSRF protection**.
3. Distinguish safe HTTP methods (`GET`, `HEAD`, `OPTIONS`, `TRACE`) from unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`), and understand why **GET must not produce side effects**.
4. Understand `CsrfFilter`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository`, `CsrfTokenRequestHandler`, the `_csrf` request attribute, and Spring Security's token masking/BREACH protection mechanism.
5. Build Thymeleaf forms for login, logout, and business operations with valid tokens; understand the difference between auto-inserted tokens and manual hidden fields.
6. Thoroughly test **valid, missing, invalid, and stale tokens**; verify that business operations **do not execute** when rejected.
7. Handle tokens after login/logout, upon session expiration, and in SPAs using cookie authentication.
8. Avoid disabling CSRF globally simply because the frontend uses JSON or POST tests return 403.
9. Know when Bearer token APIs genuinely may not need CSRF, and when `SameSite`/CORS/HTTPS **do not** replace token checks.

## 2. What Is CSRF and Where Does the Vulnerability Lie?

**Cross-Site Request Forgery (CSRF)** is the act of causing a victim's browser to send an unintended HTTP request to a website with which the browser has an authenticated relationship. The attacker **does not need to know the password** and usually **does not need to read the response**; tricking the victim into sending an effective request suffices.

Suppose Alice is logged into `https://bank.example.test` and her browser holds the session cookie. When Alice opens another page controlled by an attacker, that page can try submitting a form to the banking website. If the banking app only checks "whether a valid session cookie is present", it may interpret that request as a genuine request from Alice.

Example **solely to recognize the mechanism** (do not send to real systems):

```html
<!-- Risk example: a form outside the target origin can trigger a request. -->
<form method="post" action="https://bank.example.test/transfer">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="100">
</form>
```

The browser may automatically attach target cookies depending on `SameSite`, request characteristics, browser policy, and website configuration. Even if JavaScript from a foreign origin **cannot read the response** due to the Same-Origin Policy, the state-changing request may have already reached the server.

**CSRF vs. XSS:** XSS runs untrusted code within the application's origin and can read/populate CSRF tokens depending on implementation. CSRF comes from another origin to **exploit privileges the browser holds**. Both must be defended against; CSRF tokens do not fix XSS vulnerabilities.

**CSRF vs. IDOR/BOLA:** CSRF asks "was the request truly initiated deliberately by the user from a trusted UI?"; authorization asks "does the user have permission to transfer money or read this specific resource?". A valid CSRF token **never** turns an unauthorized action into a valid one.

## 3. Why Must All Three Groups Be Considered: Login, Logout, and Business Operations?

| Flow | Typical requests | Why is state worth protecting? | When CSRF is missing |
| --- | --- | --- | --- |
| **Login** | `POST /login` | Creates authentication/session, can bind victim's browser to another account | **Login CSRF**: victim is logged into attacker's account |
| **Logout** | `POST /logout` | Destroys security context and session, changes auth state | **Logout CSRF**: others force victim to log out |
| **Business ops** | `POST /transfer`, `PUT /profile`, `PATCH /order`, `DELETE /item` | Modifies balances, profiles, data, permissions, order states | Data can be altered via browser auto-sent requests |
| **Forgotten routes** | `GET /delete?id=...`, confirmation GET, data-writing callbacks | Uses a "safe" method to cause side effects | Default CSRF filter **does not block** GET |
| **Special features** | Uploads, webhooks, JSON endpoints, async job triggers | Can cause effects when credentials auto-send | Must analyze auth mechanism and call channel |

If a state-changing API lacks CSRF protection yet enforces strict authentication/roles, **it can still be vulnerable to CSRF**: requests through a real user's browser carry the authenticated session.

### 3.1. How Dangerous Is Login CSRF?

A scenario:

1. The attacker creates an account `mallory` on the application.
2. They cause Alice's browser to submit the login form with **mallory**'s credentials.
3. If the login endpoint lacks CSRF protection, Alice's browser can receive an authenticated session **under mallory's account**.
4. Alice believes she is using her personal account and enters sensitive notes, profile data, or orders.
5. Data can be saved into the account controlled by Mallory and read later.

Hence **login must still have CSRF**, even though the user is not yet logged in. Pre-login CSRF tokens are bound to a session or suitable token store; it is not a rule that "only authenticated users can obtain a token".

### 3.2. How Dangerous Is Logout CSRF?

A malicious page can cause the browser to invoke logout without Alice intending it. Common impacts include disrupting workflows, forcing re-login, losing state, or enabling further phishing tricks. Logout is a security state change and should not be executed via GET alone.

In Spring Security Servlet with CSRF enabled, **GET `/logout` normally renders a confirmation page**; a **POST `/logout` carrying a valid CSRF token** triggers the actual logout. If CSRF is disabled in configuration, default behavior can differ and risk must be re-evaluated.

### 3.3. Business Operations Are Not Just POST

Some easily overlooked URLs:

- `POST /account/change-email`, `POST /payment/send`;
- `PUT /api/settings`, `PATCH /api/orders/{id}`, `DELETE /api/files/{id}`;
- `POST /admin/grant-role`, `POST /export/start`, `POST /notifications/subscribe`;
- `GET /account/delete?confirm=true` or `GET /transfer?to=...` when code violates REST principles.

**Mandatory rule:** HTTP methods considered *safe* (`GET`, `HEAD`, `OPTIONS`, `TRACE`) must **not cause business-intended state changes**. If code writes data on GET, refactor the API to an unsafe method with CSRF protection; do not assume default CSRF automatically protects GET.

## 4. Synchronizer Token Pattern Mechanism

This is the standard CSRF pattern for session authentication.

```mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security + MVC
    participant R as CSRF Token Repository
    participant App as Business Logic

    B->>S: GET /transfer (with session cookie if logged in)
    S->>R: Fetch/create CSRF token bound to session
    R-->>S: CsrfToken
    S-->>B: HTML form containing hidden _csrf token

    B->>S: POST /transfer + session cookie + _csrf token
    S->>R: Fetch expected CSRF token
    S->>S: Compare request token with expected token
    alt missing or invalid token
        S-->>B: 403 Forbidden; do not invoke business logic
    else valid token
        S->>S: Check Authentication + Authorization
        S->>App: Execute valid operation
        App-->>B: Result
    end
```

The token must appear in a part of the request that an external website **cannot read or trick the browser into attaching on the victim's behalf**, such as a hidden form parameter or a custom request header actively sent by same-origin JavaScript.

The session cookie is a credential the browser can auto-send; **that cookie alone is not an active signal from the user**. CSRF tokens combine with authentication/authorization to distinguish legitimate requests.

### 4.1. Tokens Must Be Secret and Unpredictable

A CSRF token must be generated via an appropriate cryptographic random mechanism, bound to the session/transaction per design, validated server-side, and never leaked in URLs, logs, or referrers. Never hardcode token values in pre-built HTML or share a single token across all accounts.

**Practical note:** CSRF tokens are not necessarily rotated after **every** request in default configurations. Spring Security has strategies to load/save tokens and clear them on authentication success and logout; actual lifecycle depends on the repository. A token can remain valid across multiple form submissions within the same session.

### 4.2. `CsrfFilter` Runs Before Business Controllers

Spring Security provides `CsrfFilter` to inspect requests needing CSRF protection. When a request is rejected, controllers/services **do not execute**. Therefore, tests should assert zero mutation at the business layer rather than checking only the `403` status.

Do not confuse two errors:

- Missing CSRF on POST: usually returns **403** from `CsrfFilter`, even if the user lacks permissions.
- Valid token but unauthenticated user / insufficient role: request passes CSRF yet is rejected by authentication/authorization, possibly resulting in a login redirect, 401, or 403 depending on configuration.

Checking only for `403` does not tell you whether it came from CSRF or permission policy. Separate the test cases.

### 4.3. Which Methods Require a Token by Default?

In Spring Security Servlet, **by default** the CSRF filter skips safe methods (`GET`, `HEAD`, `OPTIONS`, `TRACE`) and requires a token for other methods.

| HTTP method | CSRF by default? | Notes |
| --- | --- | --- |
| GET | No | Must be read-only; never use for delete/approve/transfer |
| HEAD | No | Must not cause side effects |
| OPTIONS | No | CORS preflight has separate logic; does not open real POSTs |
| TRACE | No | Consider disabling at server level if unneeded |
| POST | Yes | Includes login, logout, payment, update |
| PUT | Yes | Resource update |
| PATCH | Yes | Partial update |
| DELETE | Yes | Resource deletion |

If the app enables `HiddenHttpMethodFilter`, method override, gateway method rewriting, or multiple filter chains, verify **the method seen by security** and the method handled by MVC. Do not assume that "because the UI uses HTML forms", all business actions strictly use POST.

## 5. Key CSRF Classes in Spring Security

### 5.1. `CsrfTokenRepository`

Spring Security stores expected tokens in `HttpSession` by default via `HttpSessionCsrfTokenRepository`. It is responsible for generating, loading, and saving/clearing tokens.

```java
// Illustrating explicit configuration in HttpSecurity:
http.csrf(org.springframework.security.config.Customizer.withDefaults());
```

That line is **not required** if the app keeps the default CSRF configuration; its purpose is showing where configuration lives.

You can use:

```java
// Custom option: same session-based CSRF model.
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        new org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository()));
```

This is **DSL illustration code**; do not combine both snippets in the same bean and do not assume changing the repository is mandatory.

### 5.2. `CsrfToken` and the `_csrf` Request Attribute

Spring Security exposes the CSRF token in request attributes for template engines/rendering, typically under the name `_csrf`, with APIs such as:

```java
CsrfToken token = (CsrfToken) request.getAttribute("_csrf");
// token.getParameterName(), token.getHeaderName(), token.getToken()
```

This snippet requires `HttpServletRequest request` and importing `org.springframework.security.web.csrf.CsrfToken` inside an actual Java method. When rendering templates, `_csrf.parameterName` and `_csrf.token` can populate the hidden input.

### 5.3. `CsrfTokenRequestHandler` and BREACH Masking

Spring Security 6.x uses **deferred CSRF tokens** and a `CsrfTokenRequestHandler`; the common default uses `XorCsrfTokenRequestAttributeHandler` to mask the token when written into responses, mitigating **BREACH**.

Key distinctions:

- Token values rendered in HTML can **differ across responses**, even when the underlying expected token in the repository stays the same.
- The handler knows how to resolve the masked token when the request is submitted back.
- Do not write tests comparing raw bytes of two hidden inputs and conclude the CSRF token rotated or failed.
- If the frontend needs to read the **raw CSRF token from a cookie** to send via a custom header, combining `CookieCsrfTokenRepository` and the request handler must be configured properly; never drop BREACH protection arbitrarily just to make a JavaScript snippet work.

### 5.4. Tokens Are Cleared After Authentication and Logout

Spring Security uses `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` to clear old tokens at relevant transitions. After successful login or logout, especially in SPAs, the client may need to **fetch a fresh CSRF token** before sending the next POST/PUT/PATCH/DELETE request.

This explains a common bug: the login API succeeds, yet the very next POST returns 403 because the SPA kept the old cleared token. The fix is **refreshing the token from a trusted source** after authentication state transitions, not disabling CSRF.

## 6. Building a Runnable Spring Boot Practice Lab

Let's build a simple Web MVC application without a database or real financial transactions. It provides:

- `GET /login`: custom Thymeleaf login page, accessible unauthenticated;
- `POST /login`: handled by Spring Security form login filter, requires CSRF;
- `GET /transfer`: business form page (logged-in users only);
- `POST /transfer`: accepts a simulated point amount, checks authenticated/role + CSRF, increments an **in-memory counter**;
- `POST /logout`: handled by Spring Security `LogoutFilter`, requires CSRF;
- `GET /error`: Boot error endpoint when needed.

The demo's goal is verifying **a simulated transaction is not recorded when the token is missing or invalid**, not designing a real money-transfer system.

### 6.1. Project Structure

```text
csrf-forms-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/csrf/
    │   │   ├── CsrfFormsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── TransferService.java
    │   │   └── PageController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── login.html
    │           └── transfer.html
    └── test/java/demo/csrf/
        └── CsrfFormsTest.java
```

Requires **JDK 17+** and Maven 3.9+, with Spring Boot parent `3.5.0` for aligned dependencies. In real deployments, use supported patch versions and verify compatibility.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>csrf-forms-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

### 6.3. Main Class

`src/main/java/demo/csrf/CsrfFormsApplication.java`:

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfFormsApplication.class, args);
    }
}
```

### 6.4. SecurityConfig: CSRF Always Enabled

`src/main/java/demo/csrf/SecurityConfig.java`:

```java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/login", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/transfer")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/transfer")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/transfer", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

Explanation:

1. `GET /login` is public so unauthenticated users can fetch the form and CSRF token.
2. `formLogin(...loginPage("/login").permitAll())` lets Spring Security handle `POST /login` and auth-related URLs, **without disabling CSRF**. `permitAll` allows accessing login; it does not mean login POST skips CSRF.
3. `GET /transfer` requires authentication; `POST /transfer` requires `ROLE_USER` authority and a CSRF token.
4. `logout(...)` uses `LogoutFilter`; do not write a manual `@PostMapping("/logout")`. With CSRF enabled, POST logout performs proper cleanup.
5. `anyRequest().denyAll()` locks down unapproved routes. Real products add rules as needed for static assets, other endpoints, etc.
6. `csrf(Customizer.withDefaults())` is explicit configuration. Spring Security already **enables CSRF by default** for Servlet web apps unless disabled.
7. Account `alice` and the fixed password are for local demo only; production needs proper identity systems, hashing, and secret management.

**Never call `csrf.disable()` in form/session-cookie apps** just to make business POSTs succeed. When a CSRF token is missing, a 403 error is a sign that protection is working, not a bug to "bypass".

### 6.5. Service Recording Simulated Business Operations

`src/main/java/demo/csrf/TransferService.java`:

```java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class TransferService {

    private final AtomicInteger acceptedRequests = new AtomicInteger();

    public int accept(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        return acceptedRequests.incrementAndGet();
    }

    public int count() {
        return acceptedRequests.get();
    }

    // Used only in tests.
    public void reset() {
        acceptedRequests.set(0);
    }
}
```

This service **transfers no money, holds no customer data, and uses no database**. `AtomicInteger` serves as an observable counter in tests. Real systems need object-level authorization, validation, transactions, idempotency, auditing, and proper replay protection; CSRF tokens solve only one slice of request security.

### 6.6. Controller Rendering Forms and Handling Business Logic

`src/main/java/demo/csrf/PageController.java`:

```java
package demo.csrf;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

@Controller
public class PageController {

    private final TransferService service;

    public PageController(TransferService service) {
        this.service = service;
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/transfer")
    public String transferForm() {
        return "transfer";
    }

    @PostMapping("/transfer")
    @ResponseBody
    public Map<String, Object> transfer(
            @RequestParam("amount") int amount,
            Authentication authentication) {

        if (amount <= 0 || amount > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid amount");
        }

        int recordNumber = service.accept(amount);
        return Map.of(
            "status", "accepted",
            "recordNumber", recordNumber,
            "recordedBy", authentication.getName(),
            "amount", amount
        );
    }
}
```

For a valid POST, the returned JSON looks like:

```json
{
  "status": "accepted",
  "recordNumber": 1,
  "recordedBy": "alice",
  "amount": 100
}
```

That is the **expected result when the counter starts at 0**, not output captured from running a server in this lesson. If the CSRF token is missing or wrong, the controller should not be invoked and `acceptedRequests` must not increment.

### 6.7. Login Template

`src/main/resources/templates/login.html`:

```html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org" lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sign in</title>
</head>
<body>
<h1>Sign in</h1>

<p th:if="${param.error}">Invalid username or password.</p>
<p th:if="${param.logout}">You have been logged out.</p>

<form th:action="@{/login}" method="post">
  <label>Username
    <input type="text" name="username" autocomplete="username" required>
  </label>
  <label>Password
    <input type="password" name="password"
           autocomplete="current-password" required>
  </label>
  <button type="submit">Sign in</button>
</form>
</body>
</html>
```

In Spring MVC + Thymeleaf integrated with `RequestDataValueProcessor`, using `th:action` on a POST form lets Thymeleaf **automatically insert the hidden CSRF field** per Spring Security's mechanism. Do not add a **second hidden `_csrf`** to the same form when auto-insertion already works. Inspect rendered HTML in integration tests/browsers; do not judge solely by template source and assume the request lacks a token.

**If not using Thymeleaf or if your template engine does not auto-insert:** render the token explicitly into the form, for example:

```html
<!-- Illustrative sample for templates without CSRF auto-insertion. -->
<form action="/login" method="post">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <input name="username">
  <input name="password" type="password">
  <button type="submit">Sign in</button>
</form>
```

`TOKEN_FROM_SERVER` **is only an illustrative placeholder**, not deployable code: obtain the value from `CsrfToken` attached to the request by the framework, such as `_csrf.token`, and get the name from `_csrf.parameterName` if customized. With a non-root context path, build action URLs via the framework's URL builder rather than hardcoding mismatched paths.

### 6.8. Business Operation and Logout Template

`src/main/resources/templates/transfer.html`:

```html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org" lang="en">
<head>
  <meta charset="UTF-8">
  <title>Simulated transfer</title>
</head>
<body>
<h1>Simulated points transfer</h1>
<p>Learning example: no real money is transferred.</p>

<form th:action="@{/transfer}" method="post">
  <label>Points amount
    <input type="number" name="amount" min="1" max="1000"
           value="100" required>
  </label>
  <button type="submit">Submit operation</button>
</form>

<form th:action="@{/logout}" method="post">
  <button type="submit">Log out</button>
</form>
</body>
</html>
```

Both the **business form** and the **logout form** use POST with `th:action`. In standard MVC/Thymeleaf configurations, automatic hidden CSRF field insertion applies to both. Do not turn logout into:

```html
<!-- DO NOT use a GET link as a state-changing action. -->
<a href="/logout">Log out now</a>
```

With CSRF enabled, `GET /logout` may only show a confirmation page; submitting POST with a token represents the logout action. A link leading to a **confirmation page** differs from a GET link that logs out directly.

### 6.9. Properties for the Demo

`src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
spring.thymeleaf.cache=false
```

In production, use **HTTPS** and **Secure** cookies:

```properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`Secure`, `HttpOnly`, and `SameSite` mitigate their own respective risks; **they do not replace CSRF tokens** when the app accepts auto-sent browser credentials. Local demos use HTTP for convenience; never copy that choice to production.

## 7. Test Suite Thoroughly Checking All Three Form Groups

Create `src/test/java/demo/csrf/CsrfFormsTest.java`:

```java
package demo.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfFormsTest {

    @Autowired MockMvc mvc;
    @Autowired TransferService service;

    @BeforeEach
    void reset() {
        service.reset();
    }

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(
                formLogin().user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void loginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-demo"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithValidCsrfCreatesAuthenticatedSession()
            throws Exception {
        MockHttpSession session = login();
        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void businessPostWithoutCsrfIsRejectedBeforeService()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .param("amount", "100"))
            .andExpect(status().isForbidden());

        assertThat(service.count()).isZero();
    }

    @Test
    void businessPostWithInvalidCsrfDoesNotMutate()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .with(csrf().useInvalidToken())
                .param("amount", "100"))
            .andExpect(status().isForbidden());

        assertThat(service.count()).isZero();
    }

    @Test
    void businessPostWithValidCsrfSucceeds() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/transfer")
                .session(session)
                .with(csrf())
                .param("amount", "100"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.recordedBy").value("alice"))
            .andExpect(jsonPath("$.recordNumber").value(1));

        assertThat(service.count()).isEqualTo(1);
    }

    @Test
    void businessPostWithCsrfButWithoutLoginCannotMutate()
            throws Exception {
        mvc.perform(post("/transfer")
                .with(csrf())
                .param("amount", "100"))
            .andExpect(status().is3xxRedirection());

        assertThat(service.count()).isZero();
    }

    @Test
    void getFormIsReadOnly() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());

        assertThat(service.count()).isZero();
    }

    @Test
    void logoutWithoutCsrfCannotEndSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mvc.perform(get("/transfer").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void logoutWithCsrfInvalidatesCurrentSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertThat(session.isInvalid()).isTrue();

        // Old session is invalid so DO NOT pass it back to MockMvc.
        mvc.perform(get("/transfer"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginFormRenders() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk());
    }
}
```

**What this test suite proves:**

- `POST /login` without a token gets **403**, whereas Spring Security Test's `formLogin()` automatically sends a valid CSRF token and authenticates successfully.
- `POST /transfer` with missing or invalid token gets **403**. More importantly, `service.count()` remains **0**: the operation had no side effect.
- A valid token **without authentication** still cannot execute business operations. This proves CSRF **does not replace authentication**.
- Only a valid token, valid user, and matching authorization rules get recorded.
- `GET /transfer` causes no side effect.
- `POST /logout` without a token does not invalidate the session; POST with a token invalidates the session and redirects to login, without writing a custom logout controller.
- Tests use a real `MockHttpSession` produced by form login rather than solely using `@WithMockUser` to inject a fake identity while skipping the login/session lifecycle.

To verify Thymeleaf auto-inserts tokens, inspect HTML responses from `GET /login` and `GET /transfer` and assert POST forms contain the hidden `_csrf` parameter or equivalent configured name. End-to-end tests in real browsers also verify Path/SameSite/cookies and browser token submission.

### 7.1. Running Tests and Server

```bash
mvn test
mvn spring-boot:run
```

When run successfully, the class above contains **10 `@Test` methods**, expected to all pass under the exact example configuration. This is an **expectation from code analysis**, not a live Maven log executed inside this lesson.

### 7.2. Manual Walkthrough

1. Open `http://localhost:8080/login` in a browser; observe the rendered HTML form with the hidden CSRF token.
2. Log in with `alice` / `alice-demo`; the browser is redirected to `/transfer`.
3. Enter points `100` and submit; response JSON shows `status=accepted` and the counter increments.
4. Craft a manual POST request **in an authorized local environment** while omitting the token; expect 403 and no counter increment.
5. Open `/transfer` again and submit the logout form; the browser receives a `/login?logout` redirect and the current session is invalidated.
6. Try accessing `/transfer` unauthenticated; you should be redirected to login.

**Do not simply run `curl -X POST` without cookies/tokens and conclude CSRF is blocking logged-in users.** Keep the same cookie jar, fetch the CSRF token from the server, and compare responses/side effects. When running behind custom domains/reverse proxies, also verify Path/Domain/SameSite/Secure so real browsers send tokens and cookies accurately.

## 8. Debugging 403 Errors: CSRF or Authorization?

A `403 Forbidden` error does not specify why the request was denied. Investigate systematically:

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `POST /login` returns 403 despite right password | Missing/invalid CSRF token | GET login page, inspect hidden CSRF field, test `with(csrf())` |
| `POST /transfer` returns 403 when logged in | Invalid/missing token or insufficient role | Test separately with/without CSRF and with/without role |
| POST succeeds in Postman yet browser form fails | Postman has different headers/tokens, cookie path, or session | Compare exact cookie jars, tokens, and content types |
| Form left open long, submitted after 30 min gets 403 | Session/expected token expired | Reload form/token, design timeout handling |
| SPA logs in, then next POST returns 403 | Old token cleared on authentication success | Fetch fresh CSRF token after login |
| Valid logout, then SPA POST gets 403 | Old token cleared after logout | Refresh CSRF token per post-logout flow |
| GET modifies data even with CSRF enabled | Default CSRF filter does not block GET | Fix HTTP contract: use POST/PATCH/DELETE |
| POST gets 403 even with valid token | Security role/permission or another filter rule | Check authorities, CSRF strategy, method security |
| Disabling CSRF makes POST work | Broken token integration, **not a reason to disable CSRF** | Fix form/template/client, keep protection |
| API POST using Bearer header still hits CSRF | A filter chain still applies CSRF or API uses cookies | Analyze architecture; narrow matcher if truly safe |

In tests, distinguish:

- `csrf().useInvalidToken()`: sends a bogus token to verify rejection;
- `csrf().asHeader()`: sends a valid token in a header instead of a form parameter, matching AJAX;
- Omitting `with(csrf())`: tests missing-token scenarios;
- `with(user(...))` or `@WithMockUser`: mocks authentication, not replacing real form-login/session tests.

## 9. Login, Logout, and CSRF Token Changes in SPAs

SPAs commonly call JSON endpoints and send session cookies via `fetch`:

```javascript
// Illustrative snippet; csrfToken must come from a trusted backend.
await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});
```

Points to remember:

1. Browsers may **auto-send session cookies** per credentials policy; having a JSON body does not categorically eliminate CSRF.
2. CSRF tokens must come from the server, never generated as random client strings hoping the server accepts them.
3. Spring Security can read tokens from the `_csrf` parameter or matching headers (such as `X-CSRF-TOKEN`/`X-XSRF-TOKEN` depending on handler/repository configuration).
4. Tokens must be fetched after app initialization, **after successful login**, and **after successful logout** when old tokens are cleared.
5. Avoid putting tokens in URLs/query strings as they can leak through history, referrers, proxies, or logs.
6. If using CORS, configure allowed origins explicitly; **CORS is not CSRF protection**.

### 9.1. A `/csrf` Endpoint When the Frontend Needs a Token

One Spring Security-guided integration exposes an endpoint for clients to actively fetch a token:

```java
// Illustrative method: place inside a real app's @RestController.
@GetMapping("/csrf")
public org.springframework.security.web.csrf.CsrfToken csrf(
        org.springframework.security.web.csrf.CsrfToken csrfToken) {
    return csrfToken;
}
```

This snippet **does not belong to the runnable demo in section 6**, only illustrating an SPA/mobile integration pattern; add a `permitAll` rule if the frontend must call it pre-login, control CORS/caching, and handle BREACH masking/cookie repositories properly. After login/logout, the frontend calls the endpoint again to get a new token.

Do not assume `/csrf` itself "grants API access": it only lets the client retrieve a CSRF token. Authorization on every POST/PUT/PATCH/DELETE must still rely on the principal and business policies.

### 9.2. Can `CookieCsrfTokenRepository` Be Used?

If JavaScript frontends need to read a token from a cookie such as `XSRF-TOKEN` and echo it in an `X-XSRF-TOKEN` header, Spring Security provides `CookieCsrfTokenRepository`. When JS must read the CSRF cookie, you may configure **only that CSRF cookie** as non-`HttpOnly`, while **session/authentication cookies must stay `HttpOnly`**.

However:

- Check the right `CsrfTokenRequestHandler`, because BREACH masking/deferred tokens in Spring Security 6.x may require adjusting how cookie tokens and request tokens are compared.
- Control cookie scope, SameSite, Secure, Path/Domain, and trusted JavaScript sources.
- Never treat the token sitting in a cookie as sufficient anti-CSRF defense by itself; the client must send it back in an **explicit header/parameter**, not rely solely on browser auto-attached cookies.
- Assess subdomain cookie injection risks and cases where attackers can manipulate cookies; token patterns and browser restrictions must align.
- In apps where JavaScript does not need to read tokens, the default session repository is usually simpler.

**Never call `withHttpOnlyFalse()` on `JSESSIONID`** just because an SPA example needs to read a CSRF cookie. They are two cookies with distinct purposes.

## 10. When Is CSRF Unneeded, and When Must It Be Carefully Evaluated?

### 10.1. Session Cookies and Form Login: Keep CSRF

If a site uses `JSESSIONID` or `SESSION` auto-sent by browsers, login/logout and state-changing POSTs must have CSRF protection. `SessionCreationPolicy.STATELESS` by itself **does not** prove safety if the app still uses an auto-sent cookie or browser HTTP Basic.

### 10.2. APIs Accepting Only Client-Attached Bearer Tokens

An API dedicated strictly to service-to-service or non-browser clients may not need CSRF if:

- It uses no sessions/credentials auto-sent by browsers on attack requests;
- Every request requires a Bearer token in the `Authorization` header actively placed by a legitimate client;
- There is no cookie/HTTP Basic fallback on the same route;
- Untrusted sites cannot obtain access tokens or inject authorized headers without valid authorization.

Even when omitting CSRF in this case, the API must still verify tokens, scopes, audiences, object-level authorization, and suitable rate limits.

### 10.3. Do Not Disable CSRF Globally for Hybrid Apps

The following configuration easily becomes a vulnerability:

```java
// UNSAFE EXAMPLE for form-login/cookie-auth apps.
http.csrf(csrf -> csrf.disable());
```

If a system has both cookie-based web forms and stateless Bearer APIs, analyze each **SecurityFilterChain**, **securityMatcher**, and credential model per zone, exempting CSRF only on endpoints genuinely free of risk. Ignoring `/api/**` via `csrf.ignoringRequestMatchers("/api/**")` can become a vulnerability if a cookie-authenticated endpoint is later added under that namespace.

`permitAll()` **does not** disable CSRF. The login page is public for authorization, yet login POST still needs a token. Similarly, a valid CSRF token **does not** grant roles to call admin endpoints.

## 11. SameSite, CORS, Origin, and Fetch Metadata

### 11.1. SameSite Is an Auxiliary Layer

`SameSite=Lax` or `SameSite=Strict` cookies curb many cross-site cookie-sending scenarios. However:

- Browsers have differences and navigation exceptions;
- SameSite is based on **site**, not **origin**; subdomains can be same-site yet different origins;
- Misconfiguring SameSite during SSO/third-party integrations can break flows, whereas enabling Lax does not prove every operation is CSRF-immune;
- `SameSite=None` requires `Secure` in modern browsers; session cookies must use HTTPS.

Therefore treat `SameSite` as **defense in depth**, rather than dropping CSRF tokens by default for browser sessions.

### 11.2. CORS Does Not Block All Form Submissions

CORS governs cross-origin script access to responses and preflight scenarios; a simple HTML form can normally send cross-origin requests without JavaScript reading the response. Hence restrictive CORS **does not replace** CSRF tokens. If an SPA sends `X-CSRF-TOKEN`, preflight/CORS is another control layer, and token verification is still needed.

### 11.3. Origin/Referer/Fetch Metadata

Checking `Origin`, `Referer`, or `Sec-Fetch-Site` helps detect suspicious requests and acts as an extra defense layer when implemented properly. Yet headers are absent in some clients/navigations, and proxies and browser policies vary. Do not write a fragile custom `Origin` check and delete `CsrfFilter`, especially for traditional forms/sessions.

### 11.4. HTTPS and XSS

HTTPS protects credentials/tokens in transit, not distinguishing victim-initiated requests from third-site-triggered requests. Same-origin XSS can break many CSRF token assumptions; output encoding, CSP, dependency hygiene, and template escaping remain mandatory.

## 12. Multipart, File Uploads, and Method Override

### 12.1. File Uploads

An upload form is a POST:

```html
<form action="/files" method="post" enctype="multipart/form-data">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <input type="file" name="file">
  <button type="submit">Upload</button>
</form>
```

This is an **illustrative template**; do not use static placeholders in practice. When forms/JS upload files, ensure the CSRF token accompanies the request. There is an ordering tradeoff between `MultipartFilter` and security filters: processing multipart before CSRF may create temporary files prior to token validation. With JavaScript, sending the CSRF token in a header often avoids parts of this complexity. You still need size limits, file-type validation, upload permissions, and safe storage.

### 12.2. `HiddenHttpMethodFilter`

If an HTML form submits POST with `_method=DELETE` to simulate DELETE, inspect filter ordering so Spring Security sees the effective HTTP method properly. Never assume method override is always applied or always safe; when designing new APIs, test both routing and CSRF for supported methods.

### 12.3. POSTs That "Look Like Reads" Yet Have Side Effects

Generating reports, triggering batch jobs, confirming emails, updating preferences, changing passwords, resetting MFA, clicking invite buttons, registering webhooks, marking "seen", sending notifications, etc., can mutate state even if the response is just 204 or a download link. Evaluate CSRF by **effect**, not by controller method naming or whether the response is JSON.

## 13. Common Mistakes and Fixes

| Mistake | What happens | Proper fix |
| --- | --- | --- |
| Protecting only transfer forms, skipping `POST /login` | Login CSRF binds victim to attacker's account | Keep CSRF on login POST |
| Using `GET /logout` to actually destroy sessions | Logout CSRF via navigation/image/link | Use POST logout with token |
| Using `GET /delete` because it feels "quick" | Default CSRF does not block GET | Switch to unsafe method and token |
| Login form missing hidden token in custom template | Valid password still gets 403 | Integrate token via Thymeleaf/RequestDataValueProcessor |
| Adding two `_csrf` hidden fields via auto-insert + manual | Request/parameter reading may be unpredictable | Pick one token rendering approach and inspect HTML |
| SPA keeps stale token after login/logout | Next POST returns 403 | Fetch fresh CSRF token after auth transition |
| Session timeout while form tab sits open | Expected token gone | Render clear error, refresh form/token; don't disable CSRF |
| Asserting only status 403 | Unclear which filter rejected or if side effect ran | Assert service/DB unchanged |
| Using `@WithMockUser` for all login tests | Doesn't test real `POST /login` flow | Use `formLogin()` for integration tests |
| Allowing POST with valid token while unauthenticated | CSRF token mistaken for authentication | Enforce login, roles, object permissions |
| Disabling CSRF when API returns JSON | Browser can still auto-send auth cookies | Evaluate credentials; keep CSRF if cookie-based |
| Confusing CORS with CSRF | Cross-origin HTML forms can still issue requests | Use CSRF tokens / proven defenses |
| Assuming `SameSite=Lax` suffices | Same-site different-origin or policy gaps exist | Defense-in-depth + CSRF token |
| Putting tokens in URLs | Can leak via logs/referrer/history | Send via hidden form field or header |
| Disabling `csrf` globally to make tests pass | Removes real risk control | Use Spring Security Test's `csrf()` |
| Generating CSRF tokens on frontend | Server cannot validate arbitrary client tokens | Fetch tokens issued by backend |
| Leaving session cookie non-HttpOnly to read CSRF | Session credentials exposed to XSS | Separate session cookie from CSRF cookie/endpoint |
| Using random UUID as "token" without session binding | Breaks correlation and validation | Use standard `CsrfTokenRepository` |
| Adding overly broad ignore matchers | New cookie-auth endpoints lose protection | Narrow exemptions and add regression tests |
| Protecting forms while leaving alternate API endpoints open | Attacker invokes alternate endpoint | Test all entry points/actions |
| Using HTTP in production | Tokens and cookies risk interception | HTTPS, Secure cookies, log redaction |
| Thinking CSRF tokens stop XSS | XSS can abuse same-origin tokens | Defend against XSS/CSP/output encoding separately |

## 14. Test Matrix for a Real Application

| Test case | Primary expectation |
| --- | --- |
| Anonymous GET login page | 200, form has valid CSRF token |
| POST login missing token | 403, no authentication created |
| POST login wrong token | 403, not logged in |
| POST login valid token + valid password | Login succeeds, session/Authentication created |
| POST login valid token + wrong password | Login fails, no valid authentication created |
| Anonymous business POST + valid token | Does not execute, login redirect/401 per flow |
| Authenticated business POST missing token | 403, DB/service unchanged |
| Authenticated business POST wrong token | 403, DB/service unchanged |
| Authenticated business POST valid token + missing role | 403, DB/service unchanged |
| Authenticated business POST valid token + valid role | Executes only permitted operation |
| GET business page | Read/render only, no state mutation |
| POST logout missing token | 403, session stays valid |
| POST logout valid token | Logout succeeds, session invalidated |
| Pre-login CSRF token retained post-login | Needs fresh token per version flow |
| Session timeout then submitting stale form | Does not execute; prompt page reload |
| AJAX POST sending valid header | Succeeds if authenticated/authorized |
| AJAX POST missing header/field | 403, no side effect |
| Multipart upload missing token | Business upload not processed |
| CORS preflight OPTIONS | Follows CORS policy, grants no POST access |
| Other unmapped POST with cookie auth | Not accidentally permitted by broad ignore rules |
| Browser with `SameSite=Lax` cookie | Token still needed under session-based policy |
| Bearer-only API without cookies | May exempt CSRF after proper threat-model review |
| Proxy/domain/path forwarding | Cookies, sessions, and tokens work in right scope |

In test automation, prioritize security invariants: **no side effects when CSRF is missing/invalid**, **proper side effects only when CSRF + permissions are valid**, **login and logout cannot be forced via tokenless POSTs**, and **GET never mutates**.

## 15. Code Review Checklist

- [ ] Identify authentication mechanisms: session cookies, browser Basic, custom cookies, Bearer headers, or combinations.
- [ ] Keep CSRF enabled for all unsafe browser forms, including **login** and **logout**.
- [ ] Use HTTP safe methods strictly for reads; never perform state changes via GET.
- [ ] Use tokens issued by Spring Security, never hardcoded or frontend-generated.
- [ ] Render hidden tokens in HTML forms; verify when template engines auto-insert tokens.
- [ ] For SPAs, send tokens via intentional headers and fetch fresh tokens after login/logout.
- [ ] Verify token repository/handler compatibility when switching to `CookieCsrfTokenRepository`.
- [ ] Use POST logout with CSRF; never turn GET into a direct logout action.
- [ ] Never skip role/owner/tenant authorization simply because a request carries a valid CSRF token.
- [ ] Test missing-token failures separately from missing-permission failures; record reasons in internal logs without leaking tokens.
- [ ] Never put tokens or cookies into URLs, telemetry, bug reports, or client-side logs.
- [ ] Define session timeout / stale form behavior; show refresh guidance instead of disabling CSRF.
- [ ] For multipart/HTTP method override, verify filter ordering and real server routing.
- [ ] Do not exempt CSRF via broad matchers on cookie-authenticated API areas or evolving namespaces.
- [ ] Test valid, invalid, missing, post-login/logout expired tokens, and **zero side effects** on rejection.
- [ ] Apply HTTPS, Secure/HttpOnly/SameSite, XSS defenses, and proper CORS/Origin policies.
- [ ] For public state-changing endpoints, still analyze CSRF/abuse even when login is unnecessary.

## 16. Self-Check Questions

**1. Why does `POST /login` also need CSRF when the user is not yet authenticated?**  
Because login CSRF can log a victim's browser into an attacker's account so subsequent data gets saved there; tokens are issued in a pre-login session.

**2. Why should `GET /logout` not directly perform logout?**  
Because GET can be triggered unintentionally by links or embedded content from another site; logout mutates state and requires POST/token.

**3. Why does Spring Security normally block POST but not GET via CSRF tokens?**  
Because safe methods are assumed not to change state. If GET writes data, fix the HTTP design rather than relying on the default CSRF filter.

**4. Is a valid CSRF token sufficient permission to transfer funds?**  
No. It proves a request-origin/intent condition, not Authentication, roles, or authorization on specific resources.

**5. Why must a POST with a bad token assert that the counter/DB did not change?**  
Because 403 can come from multiple filters, and security tests must prove sensitive business logic did not execute when rejected.

**6. Where does Spring Security store CSRF tokens by default in Servlet apps?**  
Typically in `HttpSession` via `HttpSessionCsrfTokenRepository`. Other repositories can be configured per architecture.

**7. Why can hidden CSRF token values differ across two GET requests?**  
Due to XOR masking/BREACH protection; the expected token in the repository has not necessarily changed.

**8. Why must SPAs fetch a fresh token after login/logout?**  
Because authentication/logout strategies may clear old tokens, rendering the client's cached token invalid.

**9. Can CSRF be disabled simply because requests use JSON?**  
No. You must evaluate whether credentials are auto-sent by browsers, what content types endpoints accept, and cross-origin risks. JSON does not guarantee safety on its own.

**10. Can CORS and SameSite replace CSRF tokens?**  
Not by default. CORS focuses on cross-origin script response access; SameSite is a cookie restriction with its own conditions and exceptions.

**11. If a stateless API uses Bearer tokens exclusively via `Authorization` headers with no cookies, might CSRF not be needed?**  
Possibly, after evaluating the threat model and ensuring browsers do not auto-attach credentials or fall back to other mechanisms; authentication/authorization must still be strict.

**12. Why is a broad `csrf().ignoringRequestMatchers("/api/**")` dangerous in a hybrid app?**  
Because a new API endpoint might use session cookies and unintentionally lack CSRF protection; exemptions must be narrow, reviewed, and regression-tested.

## 17. References

- [Spring Security — Cross Site Request Forgery (CSRF), Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token mechanics, repository/handler, BREACH, forms/SPAs, login/logout, timeouts, and configuration.
- [Spring Security — CSRF Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()`, `useInvalidToken()`.
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html): `formLogin()` auto-attaching tokens and executing authentication flow.
- [Spring Security — Testing Logout](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html): logout request builder with CSRF.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, CSRF, and session/context cleanup.
- [Spring Security — CSRF: Security Features](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): safe methods, token synchronization, SameSite, and browser principles.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, synchronizer token, signed double-submit cookie, and defense-in-depth.
