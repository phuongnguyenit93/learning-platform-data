# Custom Login Page and Static Asset Requirements in Spring Security Servlet

## Objectives

When `formLogin` is enabled in Spring Security Servlet, the application can use the framework-generated login page. In real-world applications, you usually want to **design your own `GET /login` page** and use your application's CSS, JavaScript, images, fonts, or favicon. For that page to render when there is no active login session, an HTML file alone is not enough: you must properly configure **public paths**, **the form POST processing endpoint**, **CSRF**, and **access permissions for static resources**.

After this lesson, you will be able to:

- Distinguish the **`GET /login` page** rendered by MVC from **`POST /login`** handled by a Spring Security filter.
- Configure `SecurityFilterChain` with `formLogin.loginPage(...)`, `loginProcessingUrl(...)`, `defaultSuccessUrl(...)`, and `failureUrl(...)`.
- Distinguish `authorizeHttpRequests().requestMatchers(...).permitAll()`, `formLogin().permitAll()`, and `WebSecurityCustomizer.ignoring()`.
- Publicly expose precisely the CSS/JS/images used by the login page without accidentally exposing business endpoints.
- Understand Spring Boot's `PathRequest.toStaticResources().atCommonLocations()` and the `src/main/resources/static` directory convention.
- Create a Thymeleaf page with a username/password form, CSRF token, and context-path-compatible asset links.
- Run a complete example with Java 17+ on Spring Boot 3.x/Spring Security 6.x and test it with MockMvc.
- Diagnose 302 redirect loops, 403 on POST login, 404/302 on static assets, and post-login or logout redirect issues.

The scope is **Spring MVC/Servlet**. `SecurityFilterChain` configuration is not equivalent to WebFlux's `SecurityWebFilterChain`. The example uses session-based form login and default CSRF protection; do not use demo passwords/tokens in production.

## 1. There Are Two "login" Endpoints with Two Distinct Responsibilities

A custom login page requires distinguishing at least two interactions:

1. **`GET /login`:** the browser requests the UI. A `@Controller` returns the `login.html` view. Unauthenticated users must also be allowed to view this page and load the required CSS/JS/images.
2. **`POST /login`:** the browser submits username, password, and CSRF token. By default, **`UsernamePasswordAuthenticationFilter`** (activated via `formLogin`) intercepts the request and calls `AuthenticationManager`. The `GET /login` controller **is not where passwords are verified**.

Typical flow:

~~~text
GET /dashboard (no session yet)
        |
FilterChainProxy -> SecurityFilterChain
        |
AuthorizationFilter requires authenticated
        |
ExceptionTranslationFilter / authentication entry point
        |
302 Location: /login
        |
GET /login
        |
requestMatchers("/login").permitAll()
        |
PageController.loginPage() -> templates/login.html view
        |
browser loads GET /css/login.css, /js/login.js, /images/logo.svg
        |
static requests are permitAll -> Spring MVC resource handler
        |
user fills out form
        |
POST /login + username + password + CSRF
        |
CsrfFilter validates token
        |
UsernamePasswordAuthenticationFilter
        |
AuthenticationManager / AuthenticationProvider
        |
        +-- success -> save SecurityContext/session -> redirect /dashboard
        |
        +-- failure -> redirect /login?error
~~~

In this lesson's sample configuration, `GET /login` and `POST /login` share the same URL yet **have different HTTP methods and different owners**. Do not write a `@PostMapping("/login")` that checks raw passwords yourself when Spring Security is already configured to handle `POST /login`.

If you choose `loginPage("/sign-in")` and `loginProcessingUrl("/authenticate")`, the GET page and POST request sit at two different paths. The HTML form must submit to the **exact** `loginProcessingUrl`; Spring Security does not inspect your form action to update the processing URL automatically.

## 2. Why Must the Login Page Be Accessible While Unauthenticated?

Suppose you configure:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated())
.formLogin(form -> form
    .loginPage("/login"))
~~~

If `GET /login` is not permitted, an unauthenticated user visiting a page is redirected to `/login`, which in turn still requires authentication. The result can be a **redirect loop** or an invisible form, depending on configuration. Therefore, you must permit the login page endpoint and any endpoints required for it to load.

An explicit configuration:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login").permitAll()
    .anyRequest().authenticated())
.formLogin(form -> form
    .loginPage("/login")
    .permitAll())
~~~

This is a **snippet** inside an `HttpSecurity` configuration chain; the full runnable example is in the practice section. `formLogin(...).permitAll()` permits URLs related to the form login mechanism, including the configured login page/processing URLs. Explicitly declaring `requestMatchers("/login").permitAll()` remains helpful so readers clearly see the intent and can audit the policy.

**Do not use `anyRequest().permitAll()` just to make the login page appear.** That also unintentionally makes `/dashboard`, `/admin`, `/account`, and all other URLs public. Do not use a broad rule like `/**` when only `/login` and UI assets are needed.

If you use an error URL such as `/login?error`, the query parameter does not change the path portion matched: it is still `GET /login`. Other redirect targets must still be handled consistently with your access control rules.

## 3. Static Assets: URL Paths Differ from Disk Directories

Spring Boot MVC has well-known default static locations, for example:

| File in project | URL without context path |
| --- | --- |
| src/main/resources/static/css/login.css | GET /css/login.css |
| src/main/resources/static/js/login.js | GET /js/login.js |
| src/main/resources/static/images/logo.svg | GET /images/logo.svg |
| src/main/resources/static/favicon.ico | GET /favicon.ico |
| src/main/resources/templates/login.html | **Not** directly accessed at /templates/login.html; MVC Controller renders the `login` view |

A file placed under `resources/static` is served by Spring MVC's resource handler at the corresponding public URL. Under Spring Boot's JAR packaging model, these resources are packaged on the classpath. You do not need a separate controller for each CSS or JavaScript file.

Conversely, files under `resources/templates` are **server-side templates** and must not be directly GET-accessible by clients as static files. The `login` view name is resolved and rendered by Thymeleaf when the controller returns the string `"login"`.

Other static locations may be supported by default in Spring Boot, such as `classpath:/public`, `classpath:/resources`, and `classpath:/META-INF/resources`. Settings like `spring.web.resources.static-locations` or `spring.mvc.static-path-pattern` can alter how mappings work. If an application overrides defaults, test the actual URLs rather than copying patterns blindly.

### URL Rules with a Context Path

If `server.servlet.context-path=/shop`, assets appear under `/shop/css/login.css`, not `/css/login.css` at the domain root. In Thymeleaf, use:

~~~html
<link rel="stylesheet" th:href="@{/css/login.css}">
<script defer th:src="@{/js/login.js}"></script>
<img th:src="@{/images/logo.svg}" alt="Logo">
~~~

Thymeleaf/Spring MVC generates URLs matching the context path at render time. In forms, likewise use `th:action="@{/login}"` instead of hardcoding `action="/login"` if the app may run under a non-root context path.

**Strings inside `securityMatcher`/`requestMatchers` generally match how `RequestMatcher` inspects `HttpServletRequest`**, rather than simply prepending the context path manually before every pattern. Test with real requests whenever changing servlet mappings or `static-path-pattern`.

## 4. Exposing Static Assets: Two Common Approaches

### 4.1. Using Spring Boot's `PathRequest`

When using Spring Boot Servlet with standard static locations:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/error").permitAll()
    .requestMatchers(
        PathRequest.toStaticResources().atCommonLocations()
    ).permitAll()
    .anyRequest().authenticated());
~~~

The snippet above is a **code fragment inside `HttpSecurity` configuration**, not a standalone application. `PathRequest` is a **Spring Boot** utility matching resources in common static locations (CSS, JavaScript, images, WebJars, favicon as supported by Boot). It helps avoid manually maintaining multiple URL patterns for common locations.

Important caveats:

- `PathRequest` is not available in an application that only depends on `spring-security-config` without the relevant Spring Boot modules.
- "Common locations" does not mean **every custom path in your application** is permitted.
- If you place assets under a custom path such as `/assets/**` or change static resource mappings, verify whether the matcher covers them and add explicit rules if needed.
- Do not assume an API endpoint named `/images/admin-data` automatically qualifies as a safe static file; static matchers must align with real resource mappings.

### 4.2. Using an Explicit URL List

If you prefer not to depend on `PathRequest` or want self-managed rules:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/login",
        "/error",
        "/css/**",
        "/js/**",
        "/images/**",
        "/favicon.ico"
    ).permitAll()
    .anyRequest().authenticated())
~~~

This approach is easy to read and test when static layout is controlled. However, if a business endpoint overlaps `/images/**`, an overly broad wildcard rule could expose non-static data. Keep URL structures clean and avoid colliding with REST APIs.

If only a few files are needed for the login page, you can permit exact paths like `/css/login.css`, `/js/login.js`, `/images/logo.svg`; renaming files then requires updating the config. Choose an appropriate scope without granting unintended access.

### Why Is `permitAll` Usually Better Than `ignoring`?

You may come across configurations like:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/css/**");
}
~~~

This is a **counter-example for the usual choice**, not code to add to the sample app. `ignoring()` causes the request to bypass the Spring Security filter chain; thus filters like `HeaderWriterFilter` have no chance to add security headers to that resource. By contrast, `permitAll` lets the request pass through `SecurityFilterChain`, while `AuthorizationFilter` skips requiring authentication for the permitted URL.

| Approach | Passes through security filter chain? | Requires login? | When to use |
| --- | --- | --- | --- |
| `requestMatchers("/css/**").permitAll()` | Yes, if the chain matches the request | Not under this rule | Default suitable choice for public CSS/JS/images |
| `PathRequest...atCommonLocations().permitAll()` | Yes, if the chain matches the request | Not under this rule | Spring Boot with common static locations |
| `web.ignoring().requestMatchers(...)` | Bypasses the Spring Security chain | Not checked by Spring Security | Consider only with a specific reason and full understanding of consequences |
| `anyRequest().permitAll()` | Yes | Not for any request in the chain | **Never** use just to fix a login page issue |

Do not treat `permitAll` as a guarantee that **every** filter skips the request: CSRF, custom filters, or other filters may still act according to their own rules. However, normal static GET requests are not the type of request for which `CsrfFilter` requires a CSRF token by default.

## 5. Runnable Example: Custom Login Page with Thymeleaf

We will build an application using Java 17, Spring Boot 3.3.5, compatible Spring Security 6.x managed by Boot, Spring MVC, and Thymeleaf.

**Expected results:** an unauthenticated user visiting `GET /login` sees HTML + CSS + JS + logo; `GET /dashboard` redirects to `/login`; submitting the form with valid username/password redirects to `/dashboard`; a wrong password returns to `/login?error`; logging out via `POST /logout` with CSRF returns to `/login?logout`.

### 5.1. Project Setup and Dependencies

Structure:

~~~text
custom-login-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat   (if using Gradle Wrapper)
  src/main/java/dev/example/customlogin/
    CustomLoginApplication.java
    SecurityConfig.java
    PageController.java
  src/main/resources/
    templates/login.html
    templates/dashboard.html
    static/css/login.css
    static/js/login.js
    static/images/logo.svg
  src/test/java/dev/example/customlogin/
    LoginPageIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'custom-login-demo'
~~~

`build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use the project with Gradle Wrapper to run the commands at the end of this section. Do not run `javac` on individual files without the Spring/Thymeleaf classpath, because imports outside the JDK will not be found.

### 5.2. Entry Point

File `src/main/java/dev/example/customlogin/CustomLoginApplication.java`:

~~~java
package dev.example.customlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }
}
~~~

### 5.3. `SecurityFilterChain` Configuration

File `src/main/java/dev/example/customlogin/SecurityConfig.java`:

~~~java
package dev.example.customlogin;

import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
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
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-demo-only"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(
                        PathRequest.toStaticResources().atCommonLocations()
                ).permitAll()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard", true)
                .failureUrl("/login?error")
                .permitAll());

        http.logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll());

        return http.build();
    }
}
~~~

Key lines explained:

1. **`requestMatchers("/login", "/error").permitAll()`:** allows unauthenticated users to access the login page and error endpoint. This is an intentional public scope; it does not relax `/dashboard`.
2. **`PathRequest.toStaticResources().atCommonLocations()`:** allows CSS/JS/logo placed in Boot's common static locations.
3. **`anyRequest().authenticated()`:** every other request (including `/dashboard`) must have a valid `Authentication`.
4. **`loginPage("/login")`:** Spring Security does not need to generate a default login UI; the application **is responsible for `GET /login`** and its template.
5. **`loginProcessingUrl("/login")`:** `POST /login` is handled by the login filter. You do not need and should not write a `@PostMapping("/login")` to invoke the password encoder.
6. **`defaultSuccessUrl("/dashboard", true)`:** after successful login, redirect to `/dashboard` rather than prioritizing a saved request. The `true` flag intentionally simplifies test expectations; if you want to return to the pre-login URL, use an appropriate saved-request policy.
7. **`failureUrl("/login?error")`:** when form authentication fails, redirect back to the login page with a generic error flag. Never pass sensitive usernames, passwords, or exceptions in the query string.
8. **`logoutSuccessUrl("/login?logout")`:** after successful logout, return to the login page and show a notice. Spring Security's default configuration already handles logout; no `POST /logout` controller is needed.
9. **`PasswordEncoder` and `UserDetailsService`:** the demo user is only `student` / `local-demo-only`, hashed before being stored in memory. Never hardcode real credentials in production source code.
10. **Do not disable CSRF:** a valid `POST /login` requires a token; Thymeleaf assists with injecting the token into the form as shown next.

Because there is a single `SecurityFilterChain` with a default matcher covering all requests, these URLs are authorized within the same chain. When a system has multiple chains with separate `@Order` and `securityMatcher`, ensure `GET /login`, `POST /login`, and static URLs **fall into the right chain**; a `permitAll` rule in one chain cannot rescue a request that hits another chain or no chain at all.

### 5.4. Controller Rendering the Two Templates

File `src/main/java/dev/example/customlogin/PageController.java`:

~~~java
package dev.example.customlogin;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String loginPage() {
        return "login";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }
}
~~~

Use `@Controller`, not `@RestController`, so the string `"login"` is resolved as a **view name** by Thymeleaf. With `@RestController`, the browser would only see the plain text `login` instead of HTML. By default convention, Spring Boot/Thymeleaf looks for `templates/login.html` and `templates/dashboard.html`.

The code only has `@GetMapping` methods for the login and dashboard pages. `POST /login` is the responsibility of `UsernamePasswordAuthenticationFilter` via `formLogin` configuration; `POST /logout` is the responsibility of `LogoutFilter`.

### 5.5. Custom Login Template

File `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign in</title>
    <link rel="stylesheet" th:href="@{/css/login.css}">
    <script defer th:src="@{/js/login.js}"></script>
</head>
<body>
<main class="card">
    <img class="logo" th:src="@{/images/logo.svg}" alt="Learn Java Logo">
    <h1>Sign in</h1>

    <p class="error" th:if="${param.error != null}">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>
    <p class="notice" th:if="${param.logout != null}">
        You have been signed out.
    </p>

    <form th:action="@{/login}" method="post">
        <label for="username">Username</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <button type="submit">Sign in</button>
    </form>
</main>
</body>
</html>
~~~

Notice three things:

- The form action generated by `th:action` points to **`POST /login`**, matching `loginProcessingUrl`. The two inputs have `name="username"` and `name="password"`, matching the default parameter names expected by `UsernamePasswordAuthenticationFilter`.
- When integrated with Spring MVC and Spring Security, Thymeleaf uses `RequestDataValueProcessor` on `th:action` forms with `method="post"` and **automatically inserts a hidden CSRF field**. Inspect the rendered HTML in dev to confirm a hidden input usually named `_csrf` is present. Never copy a static CSRF token into a template. If using another template engine or plain HTML forms, you must supply the current token via the framework-supported mechanism.
- `th:href`/`th:src` and `th:action` resolve the context path. If you hardcode `href="/css/login.css"`, an app deployed under `/myapp` can fail to load CSS.

The error message does not confirm whether a username exists or not, preventing account enumeration. Real deployments require appropriate validation policies, access messages, rate limiting, and localization.

### 5.6. Dashboard and Logout Page Template

File `src/main/resources/templates/dashboard.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dashboard</title>
</head>
<body>
    <h1>Chào mừng đến trang được bảo vệ</h1>
    <p>Only signed-in users can view this page.</p>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Sign out</button>
    </form>
</body>
</html>
~~~

By default with CSRF enabled, logging out via **`POST /logout`** is the proper approach; `th:action` with Spring integration automatically adds the CSRF token to the form. Do not create a `GET /logout` link expecting it to execute logout while CSRF is enabled.

**Never** arbitrarily disable CSRF just to make logout easier. When using session cookies in browsers, CSRF protection is vital for state-changing requests.

### 5.7. CSS File

File `src/main/resources/static/css/login.css`:

~~~css
:root {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: #243247;
    background: #f4f7fb;
}

body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
}

.card {
    width: min(90vw, 360px);
    padding: 2rem;
    background: white;
    border: 1px solid #dfe5ee;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.07);
}

.logo { width: 64px; height: 64px; }
label { display: block; margin-top: 1rem; }
input, button { box-sizing: border-box; width: 100%; padding: .7rem; }
button { margin-top: 1.2rem; cursor: pointer; }
.error { color: #a12b2b; }
.notice { color: #246a3a; }
~~~

This file under classpath `static/css` is served by MVC at `/css/login.css`. `SecurityFilterChain` must allow `GET` on this URL for unauthenticated users; otherwise the browser may receive a `302` to the login page instead of CSS, leaving the UI unstyled.

### 5.8. JavaScript File

File `src/main/resources/static/js/login.js`:

~~~javascript
document.addEventListener("DOMContentLoaded", () => {
    const usernameField = document.querySelector("#username");
    if (usernameField) {
        usernameField.focus();
    }
});
~~~

JS here only assists UX; never store username/password in `localStorage` or query strings, never interfere with password hashing mechanisms, and never perform authentication on the frontend.

### 5.9. Logo File

File `src/main/resources/static/images/logo.svg`:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"
     viewBox="0 0 64 64" role="img" aria-label="Learn Java Logo">
  <rect width="64" height="64" rx="12" fill="#243247"/>
  <path d="M17 21h30v6H23v10h24v6H17z" fill="#ffffff"/>
</svg>
~~~

The SVG file is served at `/images/logo.svg`. Only allow origin-verified SVGs if users can upload assets; never turn the public static directory into storage for confidential files or untrusted HTML/SVG content.

### 5.10. Running the Application

In the project with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell with the `.bat` wrapper:

~~~powershell
./gradlew.bat bootRun
~~~

When Spring Boot starts on default port 8080, open `http://localhost:8080/login`. Log in with:

~~~text
Username: student
Password: local-demo-only
~~~

This is an in-memory demo account **not for production use**. On success you are redirected to `/dashboard`. Click the Sign out button to `POST /logout` and get redirected to `/login?logout`.

Test the URLs without logging in:

~~~bash
curl -i http://localhost:8080/login
curl -i http://localhost:8080/css/login.css
curl -i http://localhost:8080/js/login.js
curl -i http://localhost:8080/images/logo.svg
curl -i http://localhost:8080/dashboard
~~~

Key results:

| URL | Typical result when unauthenticated |
| --- | --- |
| GET /login | 200, HTML containing login form |
| GET /css/login.css | 200, CSS content |
| GET /js/login.js | 200, JavaScript content |
| GET /images/logo.svg | 200, SVG content |
| GET /dashboard | 302 redirect to /login |

Actual status/headers may include extra information depending on container, Spring Security headers, proxy, and context path. The table represents the example's logical expectation, not a byte-for-byte HTTP response.

**Do not just run `curl -d username=... -d password=...` against `POST /login` and conclude the password is wrong when receiving 403.** With CSRF enabled, you must send the matching token and session cookie; a browser with Thymeleaf or `spring-security-test` is the easy way to verify the full flow.

## 6. MockMvc Testing: Login Page, Assets, CSRF, Auth, and Logout

Add file `src/test/java/dev/example/customlogin/LoginPageIntegrationTest.java`:

~~~java
package dev.example.customlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPageIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customLoginPageRendersForAnonymousUser() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"username\"")))
                .andExpect(content().string(containsString("name=\"password\"")))
                .andExpect(content().string(containsString("_csrf")));
    }

    @Test
    void staticAssetsArePublic() throws Exception {
        mvc.perform(get("/css/login.css")).andExpect(status().isOk());
        mvc.perform(get("/js/login.js")).andExpect(status().isOk());
        mvc.perform(get("/images/logo.svg")).andExpect(status().isOk());
    }

    @Test
    void dashboardRedirectsAnonymousUserToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location", endsWith("/login")));
    }

    @Test
    void validFormLoginCreatesAuthenticatedSession() throws Exception {
        MvcResult result = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        endsWith("/dashboard")))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("trang được bảo vệ")));
    }

    @Test
    void badCredentialsRedirectToPublicErrorMessage() throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "student")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login?error")));

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("không hợp lệ")));
    }

    @Test
    void loginWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "local-demo-only"))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutRequiresPostAndCsrfToken() throws Exception {
        MvcResult result = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login?logout")));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Tests are expected to pass with the stated code and dependencies. Tests use `.with(csrf())` provided by `spring-security-test` to perform a POST with a valid token; this **does not prove the frontend sent the token properly**. The `login.html` rendering test checks for `_csrf` to catch missing token integration in the rendered page; you should still test the form in a real browser.

Note when running with a context path, proxy, or different redirect strategy: the `Location` header may include the context path or an absolute URL. Tests in this lesson assume default localhost/no context path; if changed, adjust assertions to match the real URL contract.

## 7. CSRF: Public GET Does Not Mean POST Needs No Token

Permitting `GET /login` via `permitAll` is right; however, `POST /login` mutates authentication/session state, so it must typically go through CSRF protection in cookie-based browser apps.

With default Spring Security Servlet:

- `GET`/`HEAD`/`OPTIONS`/`TRACE` are normally treated as safe methods by `CsrfFilter` by default and do not require a token.
- `POST`/`PUT`/`PATCH`/`DELETE` usually require a CSRF token if the request falls under protected scope.
- The login form must submit a valid token when CSRF is enabled. A missing token can return `403` **before** `UsernamePasswordAuthenticationFilter` checks the password.
- `permitAll` on `/login` and `/css/**` does not automatically disable CSRF; these are two independent concerns.
- With Thymeleaf `th:action` on a `method="post"` form, Spring integration automatically inserts the hidden CSRF token. With plain HTML or SPA/APIs, use the appropriate token issuing/reading/sending mechanism (such as `CookieCsrfTokenRepository` when properly configured and handled).

An illustrative input in **rendered** HTML, never hardcoded into a template:

~~~html
<input type="hidden" name="_csrf" value="server-generated-token-for-current-session">
~~~

The value string is purely illustrative, **not a valid token**. The token must come from the actual request/session/repository. Never write tokens into logs or public docs.

### When Using JavaScript to Submit Login

If JavaScript calls `fetch("/login", { method: "POST" ... })`, you must send form data with the exact field names, the CSRF token matching your Spring Security configuration, and proper session cookies/same-origin handling. A standard HTML form with `th:action` is simpler and better suited for learning form login.

Never place raw passwords into URL query strings. HTTPS must be enabled in real environments, with appropriate login attempt limits and anomaly monitoring. Browsers must not store raw credentials in `localStorage`.

## 8. What Happens If You Customize `loginProcessingUrl`?

Suppose you want the UI at `/sign-in` and credentials posted to `/auth/sign-in`:

~~~java
.formLogin(form -> form
    .loginPage("/sign-in")
    .loginProcessingUrl("/auth/sign-in")
    .defaultSuccessUrl("/dashboard", true)
    .failureUrl("/sign-in?error")
    .permitAll())
~~~

You need:

- A `GET /sign-in` controller rendering the view;
- An HTML form `th:action="@{/auth/sign-in}" method="post"`;
- A Spring Security chain covering `/auth/sign-in` with `UsernamePasswordAuthenticationFilter` enabled;
- Valid public rules for the page/form endpoints via `formLogin().permitAll()` or equivalent config;
- The POST carrying username/password matching the filter's parameter names plus the CSRF token;
- Error and logout-success URLs viewable while unauthenticated.

If renaming form fields to `email` and `passcode`:

~~~java
.formLogin(form -> form
    .loginPage("/sign-in")
    .loginProcessingUrl("/auth/sign-in")
    .usernameParameter("email")
    .passwordParameter("passcode")
    .permitAll())
~~~

then HTML must use `name="email"` and `name="passcode"`; changing display labels alone is not enough. `UserDetailsService` or the provider must also handle email values as login identifiers where appropriate.

Do not write a POST controller on a URL already claimed by the login filter, and do not rely on requests always reaching `DispatcherServlet`: the security filter can complete authentication and redirect before the controller.

## 9. Scenarios with Multiple `SecurityFilterChain` Beans

Suppose an app has an API chain and a web chain:

~~~text
@Order(1) -> securityMatcher("/api/**")
    -> API auth (Basic/Bearer, per requirements)
@Order(2) -> default securityMatcher for all requests
    -> Web form login + GET /login + static assets
~~~

`FilterChainProxy` chooses **the first chain matching the request**. In the example, `/login` and `/css/login.css` do not match `/api/**`, so they enter the web chain configured with `permitAll`. If a catch-all web chain is mistakenly placed at `@Order(1)`, the API chain can be shadowed. If the web chain only has `securityMatcher("/private/**")`, then `/login` and static URLs will not enter that chain as you might expect.

Resulting mistakes:

- Configuring `permitAll("/login")` on the `/api/**` chain while `GET /login` enters a different web chain → has no effect.
- `loginProcessingUrl("/auth/sign-in")` falls outside the `securityMatcher("/private/**")` of the chain holding `formLogin` → the login filter does not apply to that POST.
- Static URLs get matched first by the API chain and demand a Bearer token, causing the web login page to load without CSS/JS.
- Creating only an `/api/**` chain with no fallback; other requests may bypass the Spring Security filter chain and become a security vulnerability.

Always build a table of `endpoint → chain → authorization rule → handling filter`, instead of looking solely at a single `requestMatchers().permitAll()` line.

## 10. How to Verify Static Resources Are Actually Being Served

In the browser, open DevTools → Network and load `GET /login` in an unauthenticated session. Check at minimum:

| Request | Expected | Error signs |
| --- | --- | --- |
| GET /login | HTTP 200, Content-Type text/html | Repeated 302s or 404 |
| GET /css/login.css | 200, Content-Type text/css | 302 to login, 404, or HTML returned |
| GET /js/login.js | 200, JavaScript content | 302 or JS parse error due to HTML returned |
| GET /images/logo.svg | 200, image/svg+xml | 404, 302, or resource not packaged |
| GET /dashboard when unauthenticated | 302 Location /login | Returns 200 without authentication |
| POST /login without CSRF | Usually 403 | CSRF accidentally disabled if login response returned |

**A CSS URL returning HTTP 200 is not enough:** if it actually returns login HTML with status 200 via a proxy/fallback rewrite, the browser still will not apply the CSS. Inspect `Content-Type`, the response body, and redirected URLs. Check the Request URL, Status, and Location columns in Network.

You can test from the terminal:

~~~bash
curl -i http://localhost:8080/css/login.css
curl -I http://localhost:8080/js/login.js
curl -i http://localhost:8080/dashboard
~~~

`curl -I` uses `HEAD`; `HEAD` results can differ from `GET` if the system has special configuration. `GET` is the most important request for verifying actual body content and media types.

### Useful Logging in Development

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Logs can help identify which chain/filter handled `GET /login`, `GET /css/login.css`, or `POST /login`. Message wording and names vary by version; do not build verification workflows relying on a rigid log string. Do not leave `TRACE` enabled long-term in production, and never log `Authorization` headers, cookies, CSRF tokens, or passwords.

## 11. Common Issues and Solutions

### 11.1. Redirect Loop at `/login`

**Symptom:** the browser repeatedly reloads `/login` or reports too many redirects. **Common cause:** the login URL requires authentication, or the selected `SecurityFilterChain` lacks the proper `permitAll`. Check `SecurityFilterChain`, `securityMatcher`, and authorization rules first; never fix by calling `permitAll` on the entire application.

### 11.2. Login Page Returns 404

**Symptom:** `GET /login` returns 404 or a template error. **Cause:** called `loginPage("/login")` but forgot `@Controller` `GET /login`, used `@RestController` returning a String, placed the template in the wrong folder, or missed the Thymeleaf dependency. Distinguish "permitted access" from "having an endpoint/controller serving it."

### 11.3. CSS/JS Receives 302 or HTML Content

**Cause:** static URLs are not `permitAll`, URLs are handled by another chain, template links have the wrong context path, or a proxy rewrite interfered. Add the right URL/resource matcher, use `th:href`/`th:src`, and check Network. Do not open `/**`.

### 11.4. CSS/JS Receives 404

**Cause:** file is missing from `src/main/resources/static/...` or the URL still includes `/static`, the build did not package the file, `static-path-pattern` changed, or the template references a wrong filename. With Spring Boot's default static root, `/static/css/login.css` on the filesystem becomes `/css/login.css` in the URL.

### 11.5. `POST /login` Returns 403 Even with the Right Password

**Common cause:** missing/invalid CSRF token. Confirm the form renders hidden `_csrf`, the browser sends the relevant cookie and token, and there are no mismatched contexts/sessions. In tests use `.with(csrf())`; do not disable CSRF as a quick "fix."

### 11.6. `POST /login` Returns 404, 405, or Does Not Log In

**Cause:** form `action` differs from `loginProcessingUrl`, filter chain does not cover the POST URL, `GET` method was used, username/password parameter names differ from config, or a custom controller/filter interferes. Inspect the actual POST in Network and `UsernamePasswordAuthenticationFilter`'s matcher.

### 11.7. Entering the Correct Password Still Returns to `/login?error`

Check `UserDetailsService`, `PasswordEncoder.matches`, and valid account values; the demo password is `local-demo-only` and username is `student`. Also check form input names, `AuthenticationManager`/`Provider`, and safe exception logs. Never print raw passwords or encoded hashes in logs for debugging.

### 11.8. After Login Always Goes to Dashboard Instead of the Previous Page

The example uses `defaultSuccessUrl("/dashboard", true)`: the `true` flag **intentionally** forces redirecting to dashboard. If you want to prioritize the URL saved before login, use the appropriate saved-request policy and handler while avoiding open redirects. This is a UX decision, not a session bug.

### 11.9. Logout via a GET Link Does Not Work

With CSRF enabled, default logout typically executes only via a valid POST. Use `<form method="post">`, `th:action="@{/logout}"`, and the CSRF token. Do not switch to GET logout unless you have analyzed the risks and explicit contract.

### 11.10. Public Login Error Page Leaks Account Enumeration

Messages like "user does not exist" differing from "wrong password" can aid account enumeration. Use a generic message, retry limits, anomaly monitoring, HTTPS, and MFA as required. Never expose raw exceptions in query strings or HTML.

### 11.11. Adding Static `permitAll` Left Sensitive Files Unprotected

The public static folder is no place for private uploads, configs, secrets, backups, internal PDFs, or user data. `permitAll("/images/**")` exposes **every request matching the pattern**, regardless of whether content is sensitive. For private files, serve them through a controller/storage layer with proper authorization checks, never from the static root.

### 11.12. Using `ignoring` to "Speed Things Up" Loses Security Headers

Bypassing `FilterChainProxy` means bypassing all security filters for that request, potentially losing header hardening, logging, or custom security policies. Before optimizing, measure real traffic and prefer `permitAll`; consider a dedicated CDN/public assets architecture if needed.

## 12. Secure Implementation Checklist

Before moving a custom login page to production:

1. **Have an actual `GET /login`** and a template rendering properly for anonymous users; do not confuse it with `POST /login`.
2. **Have the exact `POST loginProcessingUrl`**, with username/password parameter names matching both form and filter.
3. **Publicize login + error/logout-success URLs** with tight scope, without expanding to dashboard/admin/APIs.
4. **Ensure CSS, JS, images, and favicon load while unauthenticated** with proper status and content types; test deep links, proxies, and context paths.
5. **Ensure `templates` are not directly exposed**, and never place secrets/private user files under the static root.
6. **Keep CSRF appropriate**, with tokens on login POST and logout POST; write tests verifying tokenless requests are rejected.
7. **Ensure redirects match UX** without loops; guard saved-request handling, `failureUrl`, and open redirects.
8. **Configure real `PasswordEncoder`/`UserDetailsService`/Provider**, never hardcode production accounts, and enforce HTTPS.
9. **Avoid duplicate POST login controllers** on the endpoint already handled by `UsernamePasswordAuthenticationFilter`.
10. **With multiple chains, test chain selection per URL**, including static assets and login processing.
11. **Protect forms against brute force and account enumeration**, avoid logging sensitive data, and enforce MFA where needed.
12. **Run integration and real-browser tests** after changes to `SecurityFilterChain`, templates, Boot/Security versions, static resource mappings, or reverse proxies.

## 13. Self-Check

**Question 1.** When calling `formLogin().loginPage("/login")`, does the framework still auto-generate a default login page at that URL? Who is responsible for `GET /login`?

**Answer:** the application must provide `GET /login` (e.g., a `@Controller` returning the `login` view); custom `loginPage` does not auto-generate an HTML template for you.

**Question 2.** Why must `GET /login` be `permitAll`, while `GET /dashboard` remains `authenticated`?

**Answer:** if the login page itself is protected, anonymous users cannot reach the form to log in and can hit a redirect loop. Dashboard is a business resource so it stays protected.

**Question 3.** If a file is located at `src/main/resources/static/css/login.css`, what is its default URL?

**Answer:** `/css/login.css`, without the `/static` segment. With a context path `/myapp`, the client-side URL is typically `/myapp/css/login.css`.

**Question 4.** Are `formLogin().permitAll()` and `web.ignoring()` the same?

**Answer:** no. `permitAll` lets the request pass through `SecurityFilterChain` and waives the authorization requirement on that URL; `ignoring` bypasses the Spring Security filter chain, losing filters and security headers on that URL.

**Question 5.** Why might a form with valid username/password receive 403 on `POST /login`?

**Answer:** the CSRF token may be missing or invalid, causing `CsrfFilter` to reject before password checking. Inspect the hidden field/token and session/cookie instead of disabling CSRF.

**Question 6.** To make the form submit to `POST /authenticate` instead of `/login`, what must change?

**Answer:** set `loginProcessingUrl("/authenticate")` and `th:action="@{/authenticate}"` in HTML; ensure the POST request belongs to the appropriate security chain.

**Question 7.** If CSS returns a redirect to `/login` while the login HTML page itself returns 200, will the page be styled?

**Answer:** usually no. The browser requests `text/css` yet receives a redirect/HTML, causing styles to be ignored or triggering a MIME error. You must permit the CSS URL and verify the response body.

**Question 8.** With an `/api/**` chain and a web chain, why might `/css/login.css` return 401?

**Answer:** the static URL may be matched earlier by the API chain or another broad chain before reaching the web chain; inspect `@Order`, `securityMatcher`, authorization, and static mappings.

**Question 9.** Should private avatars/documents be placed in `src/main/resources/static/images` with `permitAll("/images/**")`?

**Answer:** no. Only put public assets in the static root; private files require an endpoint/storage with ownership-based authorization and access control.

**Question 10.** Why does login success always go to `/dashboard` in the example, even if the user visited `/private` beforehand?

**Answer:** `defaultSuccessUrl("/dashboard", true)` forces redirecting to that path. If returning to the requested URL is desired, change the success handler/saved-request policy.

## Conclusion

Building a custom login page in Spring Security Servlet requires **properly coordinating three layers**:

- **MVC/view:** Controller serves `GET /login`; Thymeleaf renders the form and CSS/JS/image paths.
- **Spring Security:** `SecurityFilterChain` permits required public URLs, `UsernamePasswordAuthenticationFilter` processes `POST` login, `AuthenticationManager` verifies credentials, and success/failure/logout components govern redirects.
- **CSRF and resource delivery:** POST forms carry tokens, static assets are accessible anonymously, and business URLs or sensitive files are never accidentally exposed.

Test `GET /login`, each static URL via `GET`, `POST /login` with valid/invalid/missing-CSRF cases, `GET` dashboard before/after login, and `POST` logout. **A rendered page, loaded assets, and still-protected private resources** together make a complete login flow.