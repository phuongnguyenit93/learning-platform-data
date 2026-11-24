# CSRF Token in the Login Form

> **Topic:** Spring Security — authentication. **Group:** Form Login. This lesson explains why even an **unauthenticated login form** needs protection against Cross-Site Request Forgery (CSRF); how Spring Security generates, stores, injects into forms, and verifies CSRF tokens; how to implement it with the default login page and custom Thymeleaf forms; why a POST missing a token gets **403 before password verification**; how to test and handle token lifecycle after login/logout, session timeouts, and multiple filter chains. The lab uses Java 17, Spring Boot 3.5.16, and Spring Security 6.5.x. Versions are pinned for reproducibility; for new projects, choose a supported branch and keep security patches up to date.

## 1. What Will You Learn?

After this lesson, you can:

1. Distinguish **authentication**, **authorization**, **CSRF protection**, **CORS**, **SameSite cookies**, and **XSS**; understand that a CSRF token is not a password or access token.
2. Describe a **login CSRF** attack and why `POST /login` needs a token **before** `UsernamePasswordAuthenticationFilter` verifies username/password.
3. State the roles of `CsrfFilter`, `CsrfTokenRepository`, `CsrfTokenRequestHandler`, and `CsrfToken`; distinguish token storage from the rendered token value.
4. Explain the default `HttpSessionCsrfTokenRepository`, session cookies, the `_csrf` parameter, CSRF headers, and safe/unsafe HTTP methods.
5. Write a login form using Thymeleaf `th:action` so Spring Security inserts the hidden CSRF input automatically; or insert it manually via `_csrf.parameterName`/`_csrf.token` when a view technology lacks automatic support.
6. Predict the outcome of a login POST with a **missing/invalid/valid CSRF token**, regardless of whether username/password are right or wrong.
7. Understand deferred CSRF loading and `XorCsrfTokenRequestAttributeHandler` (BREACH protection) in Spring Security 6, avoiding hardcoding or blindly comparing token values across GET requests.
8. Recognize that CSRF tokens are normally cleared after **successful login** and **logout**, so SPAs/forms need to obtain a fresh token according to the lifecycle.
9. Build a Spring Boot application with a custom login view, post-login page, and logout form, along with a `MockMvc` test suite using `csrf()`/`csrf().useInvalidToken()`.
10. Diagnose HTTP 403, login redirects, 404, expired sessions, cross-origin issues, reverse proxy issues, and multiple `SecurityFilterChain` configurations.

## 2. What Is CSRF? Why Is the Login Form Also at Risk?

### 2.1. Attacks Relying on Browser-Auto-Sent Credentials

A browser can automatically attach authentication cookies to a website when a user visits or triggers certain requests to that site. A malicious website can craft an HTML form pointing to a target site and cause the victim's browser to send a request **without the victim's active intent**.

Example of a banking app using session cookies:

~~~text
Victim has an active session cookie for bank.example
  |
  +-- Opens malicious page at evil.example
          |
          +-- Malicious page auto-submits POST to bank.example/transfer
                  |
                  +-- Browser may automatically attach cookies to the request
                          |
                          +-- If the server only trusts the session cookie:
                              the money transfer may occur
~~~

A CSRF token is placed in **a part of the request that a cross-origin page cannot read and copy via normal browser mechanisms**, such as a hidden form input or a header attached by same-origin JavaScript. The server compares it against the expected token and rejects requests lacking valid proof.

**Note:** CORS, SameSite cookies, and browser controls can mitigate some attack vectors, but are not a universal replacement for CSRF protection in apps relying on browser-sent credentials. When XSS exists on the trusted origin itself, an attacker can read the token; CSRF tokens **do not** solve XSS.

### 2.2. Login CSRF Is Different from "Password Theft"

A **login CSRF** attack occurs when an attacker forces the victim's browser **to log into an attacker-controlled account** on the target application instead of the victim's own account. The victim may then assume they are using their own account and create data/actions inside the attacker's account. The attacker can later inspect data saved inside the account they own.

~~~mermaid
sequenceDiagram
    participant A as Attacker Site
    participant B as Victim Browser
    participant S as Target Application
    A->>B: Page with POST /login form
    Note over A,B: Attacker account credentials
    B->>S: Automatic POST /login without valid CSRF token
    alt CSRF check disabled
        S-->>B: Creates session logged into attacker account
        Note over B,S: Victim acts inside unintended account
    else Spring Security CSRF enabled
        S-->>B: HTTP 403, form not authenticated
    end
~~~

The attack does not even require knowing the victim's password. That explains why **"the user isn't logged in yet so CSRF isn't needed" is the wrong conclusion**. Spring Security documentation emphasizes protecting **login requests** themselves.

### 2.3. What Does CSRF Not Solve?

| Mechanism | Question it answers | Replaces login form CSRF token? |
| --- | --- | --- |
| Password verification | Do credentials match the account? | No |
| CSRF token | Did the state-changing request come from a valid client flow? | It is this mechanism |
| Session cookie | Which logged-in session does the browser hold? | No, cookies can be sent automatically |
| Authorization | Is this account permitted to act on the resource? | No |
| CORS | Which cross-origin requests may other-origin JS send/read? | Not a general replacement |
| SameSite cookie | Browser restricts cookies in certain cross-site contexts | Defense-in-depth, not a replacement in all cases |
| MFA | Confirms an additional login factor | Does not replace CSRF protection |
| XSS defense | Prevents malicious scripts from running on trusted origin | Related, but addresses a different risk |

A CSRF token **does not prove the password is correct**. A request with a valid token must still be authenticated by `AuthenticationManager`; a request with the right password but missing a token can still be blocked.

## 3. CsrfFilter Validates the Token Before Form Authentication

When CSRF is enabled, `CsrfFilter` sits in Spring Security's filter chain. For requests requiring protection, it validates the token before the request reaches `UsernamePasswordAuthenticationFilter`.

~~~mermaid
flowchart TD
    A["Browser POST /login"] --> B["FilterChainProxy selects SecurityFilterChain"]
    B --> C{"CsrfFilter: method requires CSRF?"}
    C -->|No, safe method| D["Continue filter chain"]
    C -->|Yes, e.g. POST| E["Load expected CsrfToken from repository"]
    E --> F["Resolve request token: _csrf/header"]
    F --> G{"Token present and valid?"}
    G -->|No| H["AccessDeniedHandler: typically 403"]
    G -->|Yes| I["UsernamePasswordAuthenticationFilter"]
    I --> J{"Username/password valid?"}
    J -->|No| K["AuthenticationFailureHandler"]
    J -->|Yes| L["Session/Context success handling"]
~~~

This ordering is critical when debugging: a `POST /login` returning 403 may **never have called `UserDetailsService` or `PasswordEncoder`**. Do not jump to blaming a wrong password without checking CSRF first.

### 3.1. HTTP Methods Typically Checked

With default Servlet CSRF configuration, **GET, HEAD, TRACE, OPTIONS** are treated as safe methods; other methods, including **POST, PUT, PATCH, DELETE**, generally require a CSRF token.

| Request | Under default matcher | Notes |
| --- | --- | --- |
| `GET /login` | Does not require CSRF to GET | GET page can *create and render* token into the form |
| `POST /login` | Requires token | Even for unauthenticated users |
| `POST /logout` | Requires token | Prevents forced logout |
| `GET /home` | Does not require token to GET | GET must not perform state-changing actions |
| `POST /profile` | Requires token | Even if authorization is permitAll, CSRF still checks |
| `DELETE /account` | Requires token | May also require authentication/authorization |
| `OPTIONS /api` | Usually does not require CSRF | CORS preflight is not a business action |

Never design a **GET endpoint with side effects** just to dodge CSRF. A `GET /logout` that logs users out or a `GET /delete` that deletes data breaks the safe-method assumption.

### 3.2. 403 vs. 401 and Login Redirect

- **403 from CSRF:** request token is missing or invalid; `CsrfFilter` rejects before authentication.
- **Redirect `/login?error`:** form POST passed CSRF validation, but password is wrong or account status failed; handled by form login's failure handler.
- **Redirect `/home`:** valid token and valid credentials; success handler sends user to the post-login page.
- **401:** common on HTTP Basic/Bearer endpoints when credentials are missing or invalid, not the standard expected response for browser form login.
- **404:** may happen if the login processing URL lies outside the chain or a custom GET page was not implemented.

**Do not equate 403 with lacking ROLE_ADMIN.** A 403 can also come from `MissingCsrfTokenException`/`InvalidCsrfTokenException`; identify the exact filter and request before concluding.

## 4. CsrfToken, CsrfTokenRepository, and Request Handler

Spring Security separates token responsibilities:

| Component | Role |
| --- | --- |
| `CsrfToken` | Holds parameter name, header name, and token value used in requests |
| `CsrfTokenRepository` | Generates, loads, and saves the expected token |
| `HttpSessionCsrfTokenRepository` | Default repository in Servlet form apps, storing the token in HTTP session |
| `CookieCsrfTokenRepository` | Cookie-based option, common with JavaScript frameworks; requires proper handler setup |
| `CsrfTokenRequestHandler` | Controls how the token is exposed to requests and resolved from client submissions |
| `XorCsrfTokenRequestAttributeHandler` | Default handler in Spring Security 6; protects rendered tokens via BREACH masking |
| `CsrfFilter` | Checks method, loads/resolves/compares token, and rejects or forwards |
| `CsrfAuthenticationStrategy` | Clears old tokens on authentication success |
| `CsrfLogoutHandler` | Clears old tokens on logout |

### 4.1. Default Parameter and Header Names

With standard `HttpSessionCsrfTokenRepository`:
- Form parameter name: `_csrf`.
- Header name: `X-CSRF-TOKEN`.
- Token: an unpredictable string generated and stored by the server per session/policy.

Illustrative rendered HTML example **for format understanding only**:

~~~html
<input type="hidden"
       name="_csrf"
       value="example-per-request-masked-csrf-value"/>
~~~

Never copy this example string into an application. **The server must generate and render a real token** tied to the proper flow/session; hardcoded or system-wide static tokens provide no protection.

### 4.2. Why Hidden Inputs Matter

Browsers send session cookies automatically according to cookie policy, yet an attacker-controlled page cannot automatically read **a token inside a same-origin HTML page**. Under the synchronizer-token pattern, placing the token in a body parameter or header emitted by a trusted page ensures a forged cross-origin form lacks the data required to pass the CSRF check.

Do not put tokens in query strings, redirect URLs, Referrer headers, logs, or analytics when form bodies/headers are available. Query strings easily leak into history, proxy logs, and monitoring systems.

### 4.3. A CSRF Token Is Not a Session Identifier

`JSESSIONID` is the cookie identifying the HTTP session. `_csrf` is the value checked to verify the origin of an unsafe request. They have different responsibilities:
- Browser sends the right session cookie but **no valid CSRF token**: login POST still returns 403.
- Browser sends a CSRF token from another session while the cookie points to the current session: token mismatch, rejected.
- Browser sends a valid token but wrong password: login fails.

Never copy a token arbitrarily from user A's session into user B's form expecting it to work.

## 5. The GET /login → POST /login → GET /home Cycle

In a typical setup with `HttpSessionCsrfTokenRepository`:

~~~text
GET /login
  -> CsrfFilter exposes CSRF token as request attribute when the view needs it
  -> Thymeleaf renders hidden field inside HTML form
  -> Expected token is managed via session/repository

Browser sends POST /login
  -> Browser's session cookie accompanies the request
  -> Form body contains username, password, and _csrf
  -> CsrfFilter compares tokens
  -> Only if token is OK does UsernamePasswordAuthenticationFilter check password
  -> If successful: SecurityContext is established/saved per policy

GET /home after login
  -> Authenticated session is restored
  -> Page with POST forms like logout receives a fresh valid CSRF token
~~~

### 5.1. Why Is GET Needed Before POST?

A plain login form POST sent from a blank tab or an API client without a server-issued token can return 403. In the browser flow, the **GET login page** is where a legitimate client obtains the token to submit back.

Do not remove CSRF protection just to test POST quickly with curl. For backend tests, Spring Security Test provides `csrf()`; for browsers, let Thymeleaf render the real form; for non-browser clients, design an appropriate flow based on your threat model.

### 5.2. Form Has permitAll Yet CSRF Still Runs

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll()
    );
~~~

`permitAll` allows unauthenticated users to view the page and submit requests to the login processing path per authorization policy. However, `CsrfFilter` is a separate filter. **`permitAll` is not `csrf.disable()`**. POST still requires a token.

### 5.3. What If the Custom Login Page Is Not Permitted?

Another bug: `GET /login` requires authentication and redirects to `/login` infinitely. With `loginPage("/login").permitAll()` and proper matchers/chain, this loop is avoided. Still, `permitAll` does not create a GET controller; when using a custom page, the developer must render the view.

## 6. Thymeleaf Automatically Adds the CSRF Token to POST Forms

Spring Security integrates with `RequestDataValueProcessor` so views such as **Thymeleaf** and Spring MVC form tags can automatically insert the hidden CSRF field into forms using unsafe methods.

### 6.1. Recommended Template Snippet

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8" />
  <title>Sign In</title>
</head>
<body>
  <form th:action="@{/login}" method="post">
    <label>Username:
      <input name="username" autocomplete="username" />
    </label>
    <label>Password:
      <input type="password" name="password"
             autocomplete="current-password" />
    </label>
    <button type="submit">Sign In</button>
  </form>
</body>
</html>
~~~

When Spring MVC/Thymeleaf is properly wired with Spring Security, `th:action="@{/login}"` and `method="post"` cause Thymeleaf—via the request data value processor—to **automatically inject a valid hidden CSRF input** when rendering the form.

Therefore, in the runnable template below, **do not add a second hidden field**. Both "automatic injection" and "manual hidden field" have valid uses; including both does not increase security and can create duplicate parameters causing errors.

### 6.2. Manual Token Insertion When Views Lack Auto-Integration

For view technologies or server-rendered HTML without `RequestDataValueProcessor`, read the `_csrf` request attribute and render:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}" />
~~~

This is an **alternative option**—do not attach it to a form where Thymeleaf already auto-inserts the hidden field in the main example. Expressions like `${_csrf.token}` are evaluated **inside the Thymeleaf template**, not magic strings known by client-side JavaScript.

The snippet above only works when the CSRF request attribute exists, the token is issued by the server, and the view can access it. Never construct a `CsrfToken` with a random value in a controller without saving it in the repository.

### 6.3. Pure Static HTML Forms Do Not Have CSRF Automatically

~~~html
<form action="/login" method="post">
  <input name="username" />
  <input type="password" name="password" />
  <button type="submit">Sign in</button>
</form>
~~~

If you serve a **pure static HTML file** without a server template processor or a separate token-fetching mechanism, this form **will not contain `_csrf`**. A POST with Spring Security CSRF enabled will typically return 403. Either render the token server-side or implement an explicit flow to obtain and attach the CSRF token—never disable CSRF to paper over the omission.

### 6.4. username/password Fields Are Unrelated to the CSRF Field Name

Default form login reads `username` and `password`. The hidden CSRF field is normally `_csrf`, though it follows `CsrfToken.getParameterName()` if a different repository configuration is used.

If you change `usernameParameter("email")` or `passwordParameter(...)`, update the form accordingly. If you change `loginProcessingUrl`, update `th:action`. The three values—**username, password, and CSRF token**—have three separate responsibilities.

## 7. Complete Java 17 Lab: Custom Login, CSRF, Logout, and MockMvc

This project runs on real Spring Boot and Spring Security. The goal is to observe **403 from `CsrfFilter`** before authentication and verify successful login when both CSRF and credentials are valid.

For exact reproducibility, the example uses **Spring Boot 3.5.16** (a milestone released in June 2026; currently the final OSS-supported release of the 3.5 line) and JDK 17. This is a **version-pinned lab**, not a recommendation to use an OSS end-of-support branch for new products; production systems should use a maintained branch's BOM and patches.

### 7.1. Project Structure

~~~text
csrf-form-login-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/csrflogin/
    │   ├── CsrfFormLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── PageController.java
    ├── main/resources/templates/
    │   ├── login.html
    │   └── home.html
    └── test/java/example/csrflogin/
        └── FormCsrfTests.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'csrf-form-login-lab'
~~~

### 7.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-thymeleaf` is critical: if you only include Web and Security without a template engine, a controller returning view name `login` will not render the template page. `spring-security-test` supplies the `csrf()` request post-processor for writing the required tests.

### 7.4. CsrfFormLoginApplication.java

~~~java
package example.csrflogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfFormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfFormLoginApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.csrflogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(linh);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            // CSRF is enabled by default. Shown explicitly for clarity.
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/home", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            );

        return http.build();
    }
}
~~~

Points to observe:

1. This `@Bean SecurityFilterChain` **uses no narrow `securityMatcher`**, so `GET /login`, `POST /login`, `GET /home`, and `POST /logout` all traverse the chain containing `CsrfFilter`.
2. `requestMatchers("/login", "/error").permitAll()` lets users view the login page; **it does not disable CSRF checking for POST**.
3. `loginPage("/login")` is a **custom page**. Spring Security **does not auto-generate GET**; the controller below renders it.
4. `loginProcessingUrl("/login")` lets `UsernamePasswordAuthenticationFilter` handle **POST /login**, with no `@PostMapping("/login")` needed.
5. `defaultSuccessUrl("/home", true)` makes the success redirect predictable in tests.
6. `failureUrl("/login?error")` distinguishes wrong passwords from 403 caused by missing CSRF.
7. `csrf(Customizer.withDefaults())` uses the default repository/handler for this Security line; no manual token generation is needed in `@Controller`.
8. `logoutSuccessUrl(...)` specifies the redirect after logout; POST logout with CSRF performs the actual logout.

### 7.6. PageController.java

~~~java
package example.csrflogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/home")
    public String home(Model model, Authentication authentication) {
        model.addAttribute("username", authentication.getName());
        return "home";
    }
}
~~~

The controller **only handles GET**. POST login/logout belong to Spring Security filters. A `GET /home` response contains no secrets; the username simply demonstrates authenticated state.

### 7.7. templates/login.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8" />
    <title>Sign In</title>
</head>
<body>
<h1>Sign In</h1>

<p th:if="${param.error}">Invalid username or password.</p>
<p th:if="${param.logout}">You have been signed out.</p>

<form th:action="@{/login}" method="post">
    <label>Username:
        <input type="text"
               name="username"
               autocomplete="username" required />
    </label>
    <label>Password:
        <input type="password"
               name="password"
               autocomplete="current-password" required />
    </label>
    <button type="submit">Sign In</button>
</form>

<!-- Spring Security + Thymeleaf automatically add a hidden CSRF input
     for POST forms with th:action. Do not add a manual hidden _csrf field. -->
</body>
</html>
~~~

**Explanation:**
- `th:action="@{/login}"` creates an action URL matching the app context and coordinates with `RequestDataValueProcessor`.
- `method="post"` makes the form an unsafe method requiring a CSRF token.
- The hidden `_csrf` input is inserted by Thymeleaf/Spring Security **at render time**, so it need not appear literally in template source.
- `th:if="${param.error}"` and `th:if="${param.logout}"` use query parameters to display notices.
- The browser must retain the matching session cookie from GET login to POST login; a token from a different session will normally be invalid.

### 7.8. templates/home.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8" />
    <title>Home</title>
</head>
<body>
<h1>Hello, <span th:text="${username}">user</span></h1>

<form th:action="@{/logout}" method="post">
    <button type="submit">Sign Out</button>
</form>

<!-- Thymeleaf also injects the CSRF token automatically for POST /logout. -->
</body>
</html>
~~~

After login success, `GET /home` renders a fresh logout form. In Spring Security, authentication success can **clear the previously stored CSRF token**; the new form fetches a valid token from the repository. Never save a token rendered on the login page in `localStorage` for reuse across login/logout cycles.

### 7.9. FormCsrfTests.java — Complete Tests

~~~java
package example.csrflogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormCsrfTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loggedInSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/home"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void loginPageRendersCsrfHiddenInput() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")))
                .andExpect(content().string(containsString("name=\"password\"")));
    }

    @Test
    void protectedPageRedirectsBeforeLogin() throws Exception {
        mvc.perform(get("/home"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void missingCsrfBlocksEvenCorrectCredentials() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfBlocksEvenCorrectCredentials() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf().useInvalidToken())
                    .param("username", "linh")
                    .param("password", "demo-password"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfButWrongPasswordRedirectsToError() throws Exception {
        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "linh")
                    .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void validCsrfAndCredentialsCreateSession() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("linh")));
    }

    @Test
    void postLoginHomeRendersCsrfForLogout() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void logoutPostWithoutCsrfIsForbidden() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutPostWithCsrfSucceeds() throws Exception {
        MockHttpSession session = loggedInSession();

        mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
~~~

**Deep explanation of the tests:**

- `loginPageRendersCsrfHiddenInput` verifies the **rendered HTML**, not just template source. It catches missing Thymeleaf integration or forgotten `th:action`.
- `missingCsrfBlocksEvenCorrectCredentials` and `invalidCsrfBlocksEvenCorrectCredentials` prove **CSRF is checked independently of password**.
- `validCsrfButWrongPasswordRedirectsToError` proves the request passed CSRF yet failed credential verification.
- `validCsrfAndCredentialsCreateSession` exercises the **real `UsernamePasswordAuthenticationFilter`, provider, and password encoder**.
- `postLoginHomeRendersCsrfForLogout` verifies that POST forms on post-login pages also receive hidden fields.
- The two logout tests distinguish CSRF failure from valid logout processing.
- `with(csrf())` is a Spring Security Test utility simulating a valid CSRF token; it is **not** advice to hardcode tokens into clients.

**Testing caveat:** `MockMvc` runs through Spring Security filters, yet does not simulate full multi-tab browser cookies/redirects. To verify session affinity, reverse proxies, and token rotation in deployment environments, add end-to-end browser tests.

### 7.10. Running the Example

In the `csrf-form-login-lab` directory with JDK 17+ and an appropriate Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

If using the Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

**Expectation:** all nine `@Test` methods pass under the lab configuration; exact Gradle/Boot output depends on JVM and environment, so no single static stdout is quoted. Key statuses/redirects can be summarized:

| Scenario | HTTP | Target or outcome |
| --- | --- | --- |
| GET `/login` | 200 | Custom HTML containing hidden `_csrf` |
| GET `/home` unauthenticated | 302 | Redirects to `/login` |
| POST `/login` right password, missing CSRF | 403 | CsrfFilter rejects |
| POST `/login` right password, invalid CSRF | 403 | CsrfFilter rejects |
| POST `/login` wrong password, valid CSRF | 302 | `/login?error` |
| POST `/login` right password, valid CSRF | 302 | `/home` + authenticated session |
| GET `/home` in valid session | 200 | User greeting page and logout form with token |
| POST `/logout` missing CSRF | 403 | Logout does not execute |
| POST `/logout` with valid CSRF | 302 | `/login?logout` |

You can open `http://localhost:8080/login` in a browser and view the **rendered HTML** source to inspect the hidden `_csrf` input; sign in with username `linh` and password `demo-password` locally only. **Never include real credentials or tokens in screenshots/logs/tickets**.

To observe requests in Developer Tools → Network, check:
1. GET /login returns 200 and a corresponding session cookie.
2. Form POST contains `username`, `password`, and `_csrf` parameters.
3. POST returns 302 or 403 as expected.
4. Browser follows the redirect and holds an authenticated session on success.
5. The new logout form at /home also includes a CSRF field.
6. Never copy or raw-log tokens outside your test environment.

## 8. Spring Security 6: Deferred Tokens and XOR/BREACH Protection

Two major changes compared to older Spring Security guides:

### 8.1. Deferred CSRF Token Loading

Spring Security 6 **defers loading the CSRF token** by default until it is actually needed. For a GET to a resource that does not render a token or use unsafe methods, the app may avoid loading the HTTP session solely to read a token.

When `GET /login` renders a POST form needing a hidden token, the view accesses the token, causing the repository to load/create it. This is normal behavior; it does not mean GET suddenly became a CSRF-checked request.

**Debugging consequence:** a public GET might not create a session, whereas GET login creates a session because a token was needed to render the form. Never infer "login succeeded" merely from seeing a `JSESSIONID` cookie before the user enters a password.

### 8.2. XorCsrfTokenRequestAttributeHandler

Spring Security 6 uses `XorCsrfTokenRequestAttributeHandler` by default to protect tokens written into responses against compression-based attacks such as **BREACH**. Rendered values include per-response randomness/masking, while the expected token is managed by the repository.

Common points of confusion:
- Two `GET /login` requests may render **two different hidden token values** even within the same valid session.
- Do not conclude that the session changed or CSRF broke simply from differing rendered strings.
- `XorCsrfTokenRequestAttributeHandler` knows how to unmask the submitted token on POST to compare against the expected token.
- Do not strip masking just to make tokens "easy to compare" or because a JavaScript client uses the wrong model.

**Do not manually unmask or guess XOR tokens in controllers.** Let Spring Security handle it via `CsrfTokenRequestHandler`. For SPAs reading raw cookie tokens, configure a dedicated handler following Spring Security's documentation rather than blindly copying MVC form settings for JavaScript.

### 8.3. Debugging Request Attributes in Templates

In server-rendered views, the token can appear under the `_csrf` request attribute. A Thymeleaf snippet:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}" />
~~~

Use this only when **automatic CSRF field insertion is absent** on that form. If your template uses `th:action` processed by Thymeleaf, prefer the built-in integration to avoid duplicates.

## 9. Token Lifecycle After Login and Logout

### 9.1. CsrfAuthenticationStrategy

After successful authentication, `CsrfAuthenticationStrategy` may clear the old CSRF token in the repository as a security measure. Thus, **the pre-login form token should not be reused** for POSTs after login.

Correct flow:
1. Browser receives login page and token A.
2. POST /login with A and valid credentials.
3. Authentication success may clear A; session/login lifecycle proceeds.
4. Browser is redirected to /home.
5. /home renders a new POST form; backend supplies an appropriate fresh token.
6. POST /logout or state-changing forms use the current flow's token.

You do not need to call `csrfTokenRepository.saveToken(null, ...)` manually after every login because the framework integrates the strategy in standard config. Custom authentication mechanisms must verify their lifecycle with the repository/strategy.

### 9.2. CsrfLogoutHandler

Successful logout also normally clears the old CSRF token. If a frontend SPA caches tokens in memory or cookies, it must **request a new token after logout** before the next unsafe request per policy.

The post-logout GET login page gets a chance to render a new token. Therefore, a tab left open on the login page for a long time can submit a stale token, especially if the session changed or another tab logged out/in.

### 9.3. CSRF Token Rotation Does Not Mean Password/Token Rotation

Rotating or clearing a CSRF token does not mean:
- the password changed;
- a JWT access token was revoked;
- user permissions changed;
- the user was locked;
- the server reset every HTTP session.

It is a request-forgery defense layer, distinct from credential, session, and authorization lifecycles.

### 9.4. Multi-Tab Scenarios

Tab A opens `/login` with token A; Tab B logs in successfully, changing the session/token. When Tab A submits the old form, the request may return 403 due to a stale CSRF token. UI should explain this gracefully: suggest **reloading the login page**, rather than prompting the user to keep retrying their password.

Do not fix this by accepting tokens from any session or disabling CSRF because "multiple tabs are annoying". Design proper token refresh UX and handle session timeouts cleanly as part of the product.

## 10. CookieCsrfTokenRepository and JavaScript/SPAs

`HttpSessionCsrfTokenRepository` fits server-rendered forms. `CookieCsrfTokenRepository` is a common option when JavaScript clients need to read a token from a cookie such as `XSRF-TOKEN` and send it back in the `X-XSRF-TOKEN` header.

However, **a cookie holding a token does not prove the request is valid on its own**: browsers send cookies automatically, so JavaScript must read the token under trusted same-origin conditions and send a **separate header**. The server resolves and compares them per configuration.

Comparison of cases:

| Case | Expected token storage | How it is sent |
| --- | --- | --- |
| Spring MVC + Thymeleaf form | HTTP session by default | Auto-injected `_csrf` hidden parameter |
| JSP / Spring form tags | Usually HTTP session | Hidden field emitted by tag library |
| Same-origin JavaScript fetch | Session/cookie per policy | `X-CSRF-TOKEN` or `X-XSRF-TOKEN` header |
| SPA using `CookieCsrfTokenRepository` | CSRF cookie | JS reads cookie and sends header; handler must account for BREACH/deferred |
| Pure API client without cookies/auto credentials | Depends on threat model | May not need CSRF, still needs authentication/authorization |

For SPAs, Spring Security docs warn that **the default XOR request handler and deferred tokens** require specific integration differences. Using `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript can read the cookie alters your security surface; do so only when needed, with XSS defenses, cookie policies, origin checks, CORS, and token refresh in place.

**Do not copy SPA cookie config into the Thymeleaf form lab** without a real need; it complicates the example and unnecessarily exposes the token to JavaScript.

## 11. CSRF and Login Forms Across Multiple SecurityFilterChains

If an application has:
- `@Order(1)` chain with `securityMatcher("/api/**")` for Bearer/Basic.
- `@Order(2)` catch-all chain for form login.

Then `GET /login` and `POST /login` must route into the **web chain containing `formLogin` and `CsrfFilter`**. Putting `requestMatchers("/login").permitAll()` inside the API chain cannot broaden its `/api/**` matcher.

Broken example:

~~~java
http
    .securityMatcher("/secure/**")
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

If only this chain exists, its form-login filter handles the default `/login` path, which **lies outside `/secure/**`**. Browsers may redirect to `/login` where the filter never gets to serve it; if no other controller/chain handles it, the result is **404**. That is **not** a CSRF 403.

Fix this by ensuring the GET page, POST processing URL, and logout URL are selected by the right chain, or by keeping a web catch-all chain. If using custom `loginPage("/secure/login")`, render `GET /secure/login` and align the form action with `loginProcessingUrl("/secure/login")`. Then CSRF runs inside the chain that actually handles POST.

**If an endpoint does not match a security chain, that chain's `CsrfFilter` does not run either.** Thus a matcher bug can cause both "login doesn't work" and unintended exposure of other URLs.

## 12. Troubleshooting Common Login CSRF Errors

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| GET /login 200 yet HTML lacks `name="_csrf"` | Static form, missing Thymeleaf starter, missing th:action/integration | Inspect rendered HTML; use th:action and proper template engine |
| POST /login 403 with right password | Missing/wrong/stale CSRF token | Check Network request body, session cookie, CsrfFilter, token handler |
| POST /login redirects to `?error` | CSRF passed; wrong credentials or account state | Check UserDetailsService, PasswordEncoder, failure handler |
| POST /login 302 /home | Login succeeded | Verify session and protected page, don't check only 302 |
| GET /login 404 | Missing custom GET controller or wrong chain scope | Check loginPage, securityMatcher, and MVC mapping |
| POST /login 404 | Path not handled by login filter, wrong chain, or wrong method | Check loginProcessingUrl, HTTP method, filter inventory |
| 403 only after logging in from another tab | Old token cleared/rotated | Refresh form/token and ensure session alignment |
| 403 only on one instance | Session not shared or unstable routing | Check sticky sessions / Spring Session / session store |
| 403 after long idle time | Session expired, expected token lost | Refresh login page, provide sensible timeout UX |
| GET login unexpectedly creates a session | Rendering token from HttpSession repo | Can be normal with deferred tokens |
| AJAX sends X-XSRF-TOKEN yet gets 403 | Raw cookie token vs. XOR handler mismatch in SPA setup | Follow version-appropriate Spring Security SPA guide |
| Login enters redirect loop | Login page lacks permitAll or wrong chain ownership | Configure formLogin(...).permitAll() and proper routing |
| Form has two hidden `_csrf` inputs | Manual token field + Thymeleaf auto-injection | Pick only one rendering mechanism |
| POST logout returns 403 | Missing or stale token | Use POST form with a fresh CSRF token |
| Bearer API gets 403 CSRF | API chain enforces CSRF on unsafe methods despite no cookies | Evaluate threat model and scope policy per chain |
| Cross-origin site cannot submit forged form | CSRF protection working | Do not disable protection just to allow cross-site forms |
| PasswordEncoder logs never fire | CsrfFilter blocked request earlier | Debug filter order before credential logic |

### 12.1. Debugging Questions in Order

1. Which chain does a real browser `GET /login` hit? Does it reach the right custom GET handler?
2. Does the **rendered HTML** contain a hidden `name="_csrf"` field? Was its value server-generated?
3. Does the browser send the matching session cookie from GET to POST?
4. Does the POST body carry the right parameter name? Did a proxy/JS serializer strip the token?
5. Did `CsrfFilter` reject for missing/invalid token? Per safe logs, is it 403 or a failure handler?
6. If CSRF passed, did `UsernamePasswordAuthenticationFilter` match the right URL/method/fields?
7. After authentication, which URL was requested next; were session/tokens rotated/cleared?
8. If errors happen only under load balancing, is the repository backed by shared/sticky session routing?
9. Are multiple security chains or `web.ignoring` preventing login from entering the expected filter?
10. Are there any signs of XSS or token leaks in logs, URLs, or monitoring?

### 12.2. Do Not Log Tokens for "Easier Diagnosis"

Even though a CSRF token is not a password, **it still must be protected from accidental disclosure**. Never put it in URLs, console logs, error reports, APM traces, analytics, or public issues. When debugging, log only:
- CSRF token present/absent;
- handler/repository type;
- parameter/header name (not the value);
- HTTP method/path template;
- exception class such as `MissingCsrfTokenException`, `InvalidCsrfTokenException`;
- presence/absence of an appropriate HTTP session;
- a non-secret request correlation ID.

Use local DevTools with demo data when inspecting real requests; never share screenshots containing real users' tokens.

## 13. What Does Each Test Prove?

### 13.1. Tests Using Only @WithMockUser Are Not Enough

`@WithMockUser` places a test principal into the security context to test authorization. It **does not** prove that `POST /login` traversed `CsrfFilter`, the form processing filter, BCrypt, and created a real session.

For login, issue `post("/login")` requests as in the lab using `csrf()` from Spring Security Test. For logout, `@WithMockUser` can test the logout filter in isolation, though the lab uses a session created by a real login to avoid mixing scopes.

### 13.2. Spring Security Test: Valid/Invalid/Missing CSRF

~~~java
// These snippets live inside a test class with MockMvc mvc.
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().is3xxRedirection());

mvc.perform(post("/login")
        .with(csrf().useInvalidToken())
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().isForbidden());

mvc.perform(post("/login")
        .param("username", "linh")
        .param("password", "demo-password"))
    .andExpect(status().isForbidden());
~~~

`csrf()` simulates a valid CSRF token, `useInvalidToken()` simulates a wrong token, and omitting `csrf()` simulates a missing token. These tests **do not verify HTML rendering** on their own; that is why the main test suite also asserts the hidden field on GET login.

### 13.3. Tests Should Not Assert Raw Tokens Across Two GETs Are Equal

In Spring Security 6, default XOR masking injects randomness whenever the token is rendered. Comparing:

~~~text
GET /login #1 -> hidden value A
GET /login #2 -> hidden value B
A != B
~~~

does **not prove** the session changed, the token repository regenerated, or the system is broken. Proper tests focus on:
- a form POST with a valid token from that flow is accepted;
- missing/invalid tokens are rejected;
- tokens do not leak in logs/URLs;
- login/logout follow expected token lifecycle transitions.

### 13.4. Testing Multiple Tabs and Session Timeouts

An end-to-end browser test can:
1. Open Tab A `GET /login`, observe the form CSRF.
2. Open Tab B `GET /login` sharing the same session.
3. Log in on Tab B.
4. Attempt to submit the stale form on Tab A.
5. Observe a sensible error/refresh prompt rather than disabling CSRF.
6. Log out, reopen GET login, obtain a fresh token.
7. Test an expired session or deleted cookie before POST; UX should prompt the user to reload the form rather than reporting "wrong password".

Exact details depend on cookie/session/token handling; the goal is testing **expected data and fail-closed behavior**, not forcing every flow to emit a single status code.

## 14. When Might Disabling CSRF Be Considered?

In a **browser form-login application using session cookies**, never disable CSRF for `POST /login`. Having the endpoint `permitAll` is normal and still requires protection.

A **pure non-browser API** using bearer tokens in headers that browsers never attach automatically may have a different threat model. When considering disabling CSRF:
- Identify real clients and whether credentials are automatically attached by browsers.
- Distinguish Bearer headers, cookies, HTTP Basic, mTLS, and tokens stored in cookies.
- Scope changes to a **specific chain/path** and write matching tests.
- Never apply API policy to a same-domain form login if the form uses sessions.
- Keep authentication, authorization, rate limiting, CORS, and XSS defenses intact.

Writing:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

removes `CsrfFilter` protection for the **entire chain being built**, not just a desired API POST endpoint. Do not copy this line into the lab just to let `POST /login` work without a token.

`ignoringRequestMatchers(...)` can exempt carefully analyzed paths from CSRF checks, but **never add `/login` to that list just because tests saw 403**. Fix form rendering/session flow instead.

## 15. Common Anti-Patterns

1. **"Not logged in means no CSRF risk."** Login CSRF can still force a victim into an attacker-controlled account, mixing accounts and data.
2. **"permitAll means skip CsrfFilter."** False; authorization and CSRF are separate filter concerns.
3. **"Right password means POST /login must succeed."** The CSRF token must also be valid.
4. **"403 on login means PasswordEncoder is broken."** CsrfFilter can reject before password verification.
5. **Using a static HTML form without a token when CSRF is enabled.** POST normally gets 403.
6. **Using `th:action` and also adding an identical manual hidden token.** Can create duplicate parameters.
7. **Hardcoding a token in HTML/JavaScript.** Unbound to session/repository; breaks or provides no protection.
8. **Putting the CSRF token in GET query strings.** Increases leakage via history, logs, and Referrer.
9. **Generating a token in a controller without saving it in the repository.** CsrfFilter cannot match it against an expected token.
10. **Sending only JSESSIONID and assuming that suffices for POST.** Cookies are sent automatically; CSRF requires a separate token.
11. **Reusing an old tab's token after login/logout without refreshing.** The old token may have been cleared.
12. **Comparing literal rendered tokens across GETs and claiming the session changed.** XOR/BREACH masking varies the rendered representation.
13. **Removing `XorCsrfTokenRequestAttributeHandler` to "debug easily".** Weakens compression-attack protection without proper review.
14. **Using `CookieCsrfTokenRepository.withHttpOnlyFalse()` without justification.** Unnecessarily exposes the cookie to JavaScript reads.
15. **Treating SameSite cookies as complete protection.** Browser/cross-origin semantics have limits and complex edge cases.
16. **Using HTTP GET for logout or data mutations.** Violates safe-method assumptions.
17. **Using `web.ignoring("/login")`.** Can bypass the login processing filter itself.
18. **Disabling CSRF for the whole chain to fix one missing hidden input.** Trades away security for a view bug.
19. **Not testing POST logout.** Logout normally requires a CSRF token too.
20. **Treating `@WithMockUser` as a real login filter test.** Skips form processing and credentials.
21. **Failing to preserve the right session cookie between GET form and POST.** Session-bound tokens will mismatch.
22. **Not synchronizing sessions across multiple nodes.** Causes random 403s behind a load balancer.
23. **Letting third-party scripts read tokens arbitrarily.** Leakage risk; enforce XSS/CSP/origin policies.
24. **Confusing CSRF 403 with authorization 403.** Inspect the exception/filter and request.
25. **Thinking a CSRF token is an access token.** It does not grant access in place of an `Authentication`.
26. **Changing `loginProcessingUrl` and forgetting the form action.** POST hits a different route and misses the filter.
27. **Only testing GET login 200.** Fails to verify POST token presence/validation.
28. **Adding tokens to URLs or error pages.** Risks recording secrets in logs or browser history.
29. **Providing no UX for expired sessions.** Leaves users confused by 403 after leaving a form open too long.
30. **Copying SPA JavaScript config into a Thymeleaf app unnecessarily.** Easily causes handler mismatches.

## 16. Self-Check Questions

**Q1.** Why does `POST /login` need CSRF when the user is unauthenticated?  
**Answer:** To prevent login CSRF, where an attacker forces a victim's browser to log into an attacker-controlled account, confusing account identity and data ownership.

**Q2.** Does `permitAll("/login")` remove the CSRF check?  
**Answer:** No. It only affects authorization; `CsrfFilter` still checks unsafe methods.

**Q3.** A form POST has valid username/password but lacks `_csrf`; what happens in the lab?  
**Answer:** HTTP 403. The request is blocked before credential authentication.

**Q4.** A POST has a valid CSRF token but a wrong password?  
**Answer:** `CsrfFilter` lets it pass; form authentication failure redirects to `/login?error` per the lab.

**Q5.** A POST has both a valid token and the right password?  
**Answer:** Authenticated, creates a session, and redirects to `/home` per the lab.

**Q6.** In Thymeleaf, why use `<form th:action="@{/login}" method="post">`?  
**Answer:** It generates the proper action URL and lets Spring Security/Thymeleaf automatically insert the hidden CSRF field via `RequestDataValueProcessor`.

**Q7.** Should you manually add `<input name="_csrf"...>` to a form already auto-injected by Thymeleaf?  
**Answer:** No. Use one rendering mechanism to avoid duplicates.

**Q8.** Is a CSRF token the same as JSESSIONID or a JWT?  
**Answer:** No. It proves the request carries a valid repository-backed token; it does not replace identity, session, or access tokens.

**Q9.** Why can the rendered token differ across two GETs even within the same session?  
**Answer:** `XorCsrfTokenRequestAttributeHandler` applies random masking for BREACH protection in Spring Security 6.

**Q10.** Does `GET /login` require a CSRF token to be allowed?  
**Answer:** Not under default safe methods. However, rendering the POST form may trigger creating/loading a token to embed in the HTML.

**Q11.** Where does Spring Security store the expected CSRF token in a default Servlet app?  
**Answer:** In the HTTP session via `HttpSessionCsrfTokenRepository`.

**Q12.** Why shouldn't a pre-login form token be kept for logout after login succeeds?  
**Answer:** `CsrfAuthenticationStrategy` may clear the old token; post-login pages should obtain a fresh valid token.

**Q13.** How is `POST /logout` handled when missing CSRF?  
**Answer:** Typically 403 when CSRF is enabled; logout is not executed for that request.

**Q14.** Does using a CSRF token prevent XSS on the site?  
**Answer:** No. Malicious scripts on the same origin can read tokens; XSS defense is a separate layer.

**Q15.** Can you disable CSRF simply because an endpoint serves `/api/**`?  
**Answer:** No. You must verify whether browsers auto-send cookies/Basic credentials and review the specific client policy.

**Q16.** Can a browser POST with a valid token but no password log in?  
**Answer:** No. `AuthenticationManager` still has to verify credentials.

**Q17.** What does `csrf().useInvalidToken()` represent in MockMvc?  
**Answer:** A request carrying an invalid CSRF token, expected to be rejected with 403 by `CsrfFilter`.

**Q18.** A user leaves a login tab open overnight, then POSTs and gets 403; what should you check first?  
**Answer:** Session timeout, stale token, lost/changed session cookie, and request handler—do not immediately tell the user to change their password.

## 17. Production Checklist

- [ ] Form login POST has CSRF protection; do not ignore/disable `/login` when using browser sessions.
- [ ] GET login page sits in the right `SecurityFilterChain` and has `permitAll`.
- [ ] POST login processing URL/method match the form action.
- [ ] Use Spring Security-managed CSRF tokens, never hardcoded values.
- [ ] If using Thymeleaf, `spring-boot-starter-thymeleaf` is present and `th:action` is active.
- [ ] **Rendered HTML** contains the right hidden `_csrf` field without duplicates.
- [ ] Browser preserves the matching session cookie between form GET and POST.
- [ ] Login POST with missing/wrong token returns 403; valid token + wrong password does not authenticate.
- [ ] Valid token + valid credentials establish session/authentication per policy.
- [ ] Logout uses POST with an appropriate CSRF token; never convert to GET casually.
- [ ] Mechanism exists to fetch/render fresh tokens after login/logout; multi-tab/stale forms have clear UX.
- [ ] Tokens never appear in URLs, logs, analytics, or public places.
- [ ] Enforce HTTPS, cookie policies, XSS protection, and proper CSP.
- [ ] Deferred CSRF/XOR handler kept version-appropriate; SPA cookie integration uses dedicated setup.
- [ ] Do not infer "CSRF not needed" merely from stateless/API/Bearer labels.
- [ ] Test 200/302/403 cases, session timeout, wrong password, and login/logout.
- [ ] Test in a real multi-node or shared session store environment if production uses a load balancer.
- [ ] Distinguish CSRF 403, authorization 403, authentication 401, and chain/handler 404.
- [ ] Verify supported Spring Boot/Security versions and latest security patches.

**Remember:** The CSRF token in a login form is not used to verify passwords; it confirms that a POST request came from an application-issued flow. Spring Security provides `CsrfFilter` for validation, `CsrfTokenRepository` for storing the expected token, `CsrfTokenRequestHandler` for exposing/resolving tokens, and Thymeleaf can emit the hidden field automatically. For session-based form login, **GET login page → receive token → POST token + username/password → check CSRF first → verify credentials second** is the complete chain. Maintain this protection before login, after login, and at logout.

### Source References

- Spring Security 6.5 — **CSRF (Servlet)**: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — **Form Login**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5 — **Migration: Deferred CSRF and BREACH**: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security 6.5 — **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — **SecurityFilterChain / Java Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — **CsrfFilter Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security 6.5 — **HttpSessionCsrfTokenRepository Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/HttpSessionCsrfTokenRepository.html
- Spring Security 6.5 — **XorCsrfTokenRequestAttributeHandler Javadoc**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/XorCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 — **Spring Security Test**: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.5.16 release (June 2026; last OSS 3.5.x): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- OWASP — **Cross-Site Request Forgery Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
