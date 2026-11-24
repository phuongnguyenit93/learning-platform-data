# Custom Login Page and Paths Requiring Public Access

> **Context:** Spring Security – authentication, **Form Login** group. This lesson explains how to build a custom login page with Spring MVC + Thymeleaf, distinguish the URL that **displays the form** from the URL that **processes credentials**, and configure which paths must be accessible while the user is **unauthenticated**. The complete example uses **Java 17+**, **Spring Boot 4.1.2**, Spring Security Servlet, and Thymeleaf; it covers CSRF, form login, logout, protected pages, public CSS, flow diagrams, testing, and diagnosing redirect loops.

## 1. Why Must a Custom Login Page Be Publicly Accessible?

When adding Spring Security to a web application, the common policy is: business URLs require authentication, while certain endpoints serving content needed **before authentication** must remain accessible.

The login page is the clearest example. A user without a valid session must be able to load the page containing the form to enter username and password. If the login page itself also requires authentication, the flow can redirect back to itself repeatedly:

```text
GET /dashboard (unauthenticated)
       |
       v
Security requires authentication
       |
       v
302 Location: /sign-in
       |
       v
GET /sign-in
       |
       +-- If /sign-in also requires authentication
       |       |
       |       v
       |   302 Location: /sign-in
       |       |
       |       +-- repeats -> redirect loop
       |
       +-- If /sign-in is permitAll
               |
               v
           HTTP 200, login form
```

However, **this does not mean the entire application should be public**. Only resources genuinely needed prior to login receive `permitAll`. Business endpoints such as `/dashboard`, `/account/settings`, or `/admin/**` remain protected.

A login page also typically loads CSS files, images/logos, icons, and JavaScript. If `/sign-in` is public while `/css/site.css` still requires login, the HTML may return 200 while the layout breaks or the browser receives HTML instead of CSS. Therefore, the public allowlist must be viewed across the **entire rendering flow**, not just a single URL.

## 2. Form Login Involves at Least Two Distinct URLs

In Spring Security Servlet, distinguish:

1. **Form display page (login page):** for example `GET /sign-in`. A Spring MVC `@Controller` renders a Thymeleaf template.
2. **Credential processing endpoint (login processing URL):** for example `POST /perform-login`. Spring Security's `UsernamePasswordAuthenticationFilter` receives username/password; normally **you do not need a `@PostMapping` controller for this path**.

Diagram:

```text
Unauthenticated browser
      |
      | GET /sign-in
      v
PageController.signIn()
      |
      v
templates/sign-in.html   (username, password, CSRF token)
      |
      | POST /perform-login
      v
Spring Security UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager / AuthenticationProvider
      |
      +-- invalid -> 302 /sign-in?error
      |
      +-- valid -> session/SecurityContext
                        |
                        v
             302 /dashboard or saved request
                        |
                        v
                Protected page
```

**Do not confuse:**

- `loginPage("/sign-in")` declares the login page address to redirect to when unauthenticated.
- `loginProcessingUrl("/perform-login")` is where the authentication filter **receives the POST**.
- `failureUrl("/sign-in?error")` is the redirect URL on login failure.
- `defaultSuccessUrl("/dashboard", false)` specifies the default destination when no prioritized saved request exists.
- `permitAll()` on form login allows the associated login/failure/processing URLs to be accessed without prior authentication, but **does not automatically permit all CSS, images, registration pages, or password resets**.

### Table of Required Paths

| Request | Requires prior authentication? | Handling component |
| --- | --- | --- |
| `GET /sign-in` | **No** | Spring MVC controller + Thymeleaf |
| `POST /perform-login` | **Not prior auth**; must pass CSRF and login filter | `UsernamePasswordAuthenticationFilter` |
| `GET /sign-in?error` | **No** | Same MVC controller; template renders message |
| `GET /sign-in?logout` | **No** | Same MVC controller; template renders status |
| `GET /css/site.css` | **No** | Spring Boot static resource handler |
| `GET /images/logo.svg` if login page uses it | **No** | Static resource handler |
| `GET /public/about` | **No** if content is public | Spring MVC/controller |
| `GET /dashboard` | **Yes** | Protected controller |
| `GET /admin/**` | **Requires proper role** | Authorization + controller |
| `POST /sign-out` | No prior login needed if logout config is permitAll, **still requires CSRF** | `LogoutFilter` |
| `POST /register` if present | Can be public, but needs validation/CSRF/rate limit | Registration service |
| `POST /reset-password` if present | Can be public, but must verify reset token | Password reset service |

**Public route ≠ unprotected.** `permitAll` removes the authentication requirement at the authorization layer; CSRF, input validation, rate limiting, reset token verification, security filters, and business logic must still operate.

## 3. Custom Login Page vs. Spring Security's Default Page

If you only configure `formLogin(withDefaults())` without providing a custom page, Spring Security can generate a default login page for development/testing. That page is served by a framework filter.

Calling `formLogin(form -> form.loginPage("/sign-in"))` tells Spring Security that **the application will provide** `/sign-in`. The framework does not generate a Thymeleaf file, does not add `@GetMapping("/sign-in")`, and does not know your desired layout or branding.

A minimal custom page requires:

- A **controller** returning a view name for `GET /sign-in`.
- A template file in the directory where Thymeleaf looks.
- A `method="post"` form whose action matches `loginProcessingUrl`.
- Input names matching `usernameParameter` and `passwordParameter` (default `username`, `password`).
- A valid CSRF token on form POST.
- `permitAll` rules for the login page and necessary public resources.
- Reasonable success/failure URLs that do not loop.

**No manual password handling in controllers.** Form processing belongs to the authentication filter/provider. Writing `@PostMapping("/perform-login")` to compare passwords manually and call `SecurityContextHolder` can conflict with or bypass Spring Security's mechanisms.

## 4. Authentication Flow for an Unauthenticated User

Example where a user visits `/dashboard` first:

```text
GET /dashboard (anonymous)
         |
         v
AuthorizationFilter requires authenticated()
         |
         v
ExceptionTranslationFilter triggers authentication entry point
         |
         v
302 /sign-in
         |
         v
GET /sign-in (permitAll)
         |
         v
200 HTML with form and CSRF hidden input
         |
         v
POST /perform-login
  username=an
  password=training-pass
  _csrf=<token from form>
         |
         v
UsernamePasswordAuthenticationFilter
         |
         v
AuthenticationManager / DaoAuthenticationProvider
         |
         +-- wrong password -> 302 /sign-in?error
         |
         +-- right password -> SecurityContext + session
                                     |
                                     v
                         302 /dashboard (saved request)
```

In a typical browser flow, `SavedRequestAwareAuthenticationSuccessHandler` can prioritize the URL the user requested before being redirected to login. Thus, after logging in from `/dashboard`, the app normally sends them back to `/dashboard`; if they visited the login page directly, `defaultSuccessUrl` becomes the default target.

`defaultSuccessUrl("/dashboard", false)` means do not unconditionally force dashboard in every case. Choosing `true` ignores any saved request; decide based on product UX.

### Why Does Login Use POST?

Credentials are sensitive data. Sending username/password in a GET query string can expose them in URLs, browser history, proxy logs, analytics, or Referer headers. Standard Spring Security form login processes **HTTP POST** at the login processing URL. Real applications must use HTTPS; POST alone does not encrypt network traffic.

## 5. SecurityFilterChain Configuration: Public Just Enough

The following example matches the file set shown later.

```java
package com.example.customlogin;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("an")
                .password(encoder.encode("training-pass"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        // Allow the container to display error pages properly.
                        .dispatcherTypeMatchers(DispatcherType.ERROR)
                            .permitAll()

                        // Custom MVC page for anonymous users.
                        .requestMatchers(HttpMethod.GET, "/sign-in")
                            .permitAll()

                        // Assets and genuinely public content.
                        .requestMatchers(
                                "/css/**", "/images/**",
                                "/favicon.ico", "/public/**")
                            .permitAll()

                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")

                        // Dashboard and remaining URLs require login.
                        .anyRequest().authenticated())

                .formLogin(form -> form
                        .loginPage("/sign-in")
                        .loginProcessingUrl("/perform-login")
                        .usernameParameter("username")
                        .passwordParameter("password")
                        .failureUrl("/sign-in?error")
                        .defaultSuccessUrl("/dashboard", false)
                        .permitAll())

                .logout(logout -> logout
                        .logoutUrl("/sign-out")
                        .logoutSuccessUrl("/sign-in?logout")
                        .permitAll())

                // Do not disable CSRF. Spring Security protects
                // POST /perform-login and POST /sign-out.
                .build();
    }
}
```

### Part-by-Part Breakdown

**`authorizeHttpRequests`:** rules are evaluated in declaration order; the first matching rule decides authorization. In the demo, `GET /sign-in` is public, assets and `/public/**` are public, `/admin/**` requires `ROLE_ADMIN`, and all other URLs require authentication.

**`formLogin`:** `loginPage` is the form display path; `loginProcessingUrl` is the POST handled by Spring Security's filter. `permitAll()` on form login ensures login-related URLs can reach the filter/display; it does not disable other security protections.

**`failureUrl`:** `/sign-in?error` still shares the **`/sign-in` path**; the query parameter does not require an extra controller. The template reads `param.error` to display a neutral message.

**`logout`:** `POST /sign-out` is handled by `LogoutFilter`, requiring no controller. With default CSRF, POST logout requires a token and then redirects to `/sign-in?logout`, a public page.

**`PasswordEncoder`:** the demo uses BCrypt to hash the in-memory password. Never use plaintext or `{noop}` in production. User `an` has `ROLE_USER`, so they can access dashboard but cannot open `/admin/**`.

**`DispatcherType.ERROR`:** Spring Boot can use an error dispatch to `/error`. When authorization checks ERROR dispatches too, permitting `DispatcherType.ERROR` allows error pages to render rather than masking errors behind a confusing redirect/403. This does not make business URLs public.

**No `csrf.disable()`:** a form-login app uses session cookies, making CSRF protection essential. Thymeleaf integrated with Spring Security injects the hidden token into POST forms via `th:action`.

### Why Not Use requestMatchers("/**").permitAll()?

Because that makes every URL look public, including account settings or admin routes if placed before restrictive rules. `permitAll` for login URLs and assets must be **narrow**, scoped strictly to what is needed before authentication.

## 6. Complete Spring Boot 4.1.2 + Thymeleaf Example

We build an application with:

- `GET /sign-in`: custom login page.
- `POST /perform-login`: authentication processing endpoint handled by Spring Security.
- `GET /dashboard`: private page for logged-in users.
- `GET /public/about`: public page.
- `GET /css/site.css`: public CSS.
- `POST /sign-out`: CSRF-protected logout.
- `GET /sign-in?error` / `?logout`: status notices.

**Learning project:** Java 17+, Maven, Spring Boot 4.1.2, MVC/Security/Thymeleaf. For production, use supported versions, track security advisories, store users via a repository/identity provider, and never hardcode passwords.

### 6.1. Directory Tree

```text
custom-login-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/customlogin/
        │   ├── CustomLoginApplication.java
        │   ├── SecurityConfiguration.java
        │   └── PageController.java
        └── resources/
            ├── templates/
            │   ├── sign-in.html
            │   ├── dashboard.html
            │   └── about.html
            └── static/
                └── css/
                    └── site.css
```

No `application.properties` is needed for the basic demo: Spring Boot defaults to port 8080 unless configured otherwise.

### 6.2. pom.xml File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>custom-login-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Spring Boot parent manages compatible dependency versions. `spring-boot-starter-webmvc` provides Servlet MVC; `spring-boot-starter-thymeleaf` renders files from `src/main/resources/templates/`; Spring Security provides the filter chain, form processing, and CSRF.

### 6.3. CustomLoginApplication.java

```java
package com.example.customlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }
}
```

### 6.4. SecurityConfiguration.java

Use the complete `SecurityConfiguration` class from **Section 5**, saved to:

```text
src/main/java/com/example/customlogin/SecurityConfiguration.java
```

The class is in the same `com.example.customlogin` package as `CustomLoginApplication` so Spring Boot component scanning picks up the configuration bean. Do not add another `SecurityFilterChain` matching the same URLs without controlling order and scope.

### 6.5. PageController.java

```java
package com.example.customlogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class PageController {

    @GetMapping("/sign-in")
    String login() {
        return "sign-in";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication, Model model) {
        model.addAttribute("username", authentication.getName());
        return "dashboard";
    }

    @GetMapping("/public/about")
    String about() {
        return "about";
    }
}
```

**No `@PostMapping("/perform-login")`:** username/password go to Spring Security's `UsernamePasswordAuthenticationFilter`. The controller only serves HTML pages.

For `/dashboard`, the filter chain requires authentication before MVC invokes the method, so `Authentication` is expected to represent an authenticated user. Never place password hashes or raw authentication objects in the model; only expose safe display data.

### 6.6. templates/sign-in.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign In</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Sign In</h1>

    <p th:if="${param.error}" class="alert" role="alert">
        Invalid credentials.
    </p>

    <p th:if="${param.logout}" class="message" role="status">
        You have been signed out.
    </p>

    <form th:action="@{/perform-login}" method="post">
        <label for="username">Username</label>
        <input id="username" type="text" name="username"
               autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" type="password" name="password"
               autocomplete="current-password" required>

        <button type="submit">Sign In</button>
    </form>

    <p><a th:href="@{/public/about}">Public Information</a></p>
</main>
</body>
</html>
```

**Points to observe:**

- `th:action="@{/perform-login}"` matches `loginProcessingUrl("/perform-login")`.
- `method="post"` is the form login HTTP method.
- Input names are exact: `username` and `password`.
- Thymeleaf integrated with Spring MVC/Spring Security inserts the CSRF token into the POST form via `RequestDataValueProcessor`; inspect the **rendered HTML** to verify the `_csrf` hidden input is present.
- `th:if="${param.error}"` shows a **generic** message without revealing "whether the username exists".
- `?error` / `?logout` query flags need no separate route; the controller still handles `/sign-in`.
- CSS loads from `/css/site.css`; that path must be permitted while unauthenticated.
- `autocomplete` helps password managers and is not a security substitute for HTTPS.

**Never put raw passwords in hidden inputs, query URLs, or logs.** Never add text like "This account exists but the password is wrong" for unauthenticated users, as that aids username enumeration.

### 6.7. templates/dashboard.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dashboard</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Dashboard</h1>
    <p>Hello <strong th:text="${username}">user</strong>.</p>

    <p>This page requires a valid authenticated session.</p>

    <form th:action="@{/sign-out}" method="post">
        <button type="submit">Sign Out</button>
    </form>
</main>
</body>
</html>
```

Logout uses a **POST form**, and Thymeleaf adds the CSRF token for it as well. Spring Security's `logoutUrl("/sign-out")` handles the request; no `@PostMapping("/sign-out")` controller is needed. After logout, `/sign-in?logout` stays public so the browser can display the confirmation message.

### 6.8. templates/about.html

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>About</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="container">
    <h1>Public Page</h1>
    <p>You can read this page without logging in.</p>
    <p><a th:href="@{/sign-in}">Go to sign-in page</a></p>
</main>
</body>
</html>
```

### 6.9. static/css/site.css

```css
body {
    font-family: system-ui, sans-serif;
    background: #f7f8fc;
    color: #172033;
    line-height: 1.5;
}

.container {
    max-width: 420px;
    margin: 48px auto;
    padding: 28px;
    border: 1px solid #dce2ee;
    border-radius: 12px;
    background: white;
}

label, input {
    display: block;
    width: 100%;
    box-sizing: border-box;
}

label { margin-top: 16px; }

input {
    margin-top: 6px;
    padding: 10px;
    border: 1px solid #aeb8ca;
    border-radius: 6px;
}

button {
    margin-top: 22px;
    padding: 10px 16px;
    cursor: pointer;
}

.alert { color: #9b1c1c; }
.message { color: #205d32; }
```

Place CSS in `src/main/resources/static/css/site.css` so Spring Boot serves it at `/css/site.css`. It does not go under `templates/`. When using a CDN or static files on another host, check CORS/CSP policies, but never use `permitAll("/**")` to fix CSS loading errors.

## 7. Running the Example and Observing Results

Requirements: JDK 17+, Maven 3.9+ or the project's Maven wrapper, and network access to download Maven dependencies. At the `custom-login-demo/` root:

```bash
mvn spring-boot:run
```

If using the Maven wrapper:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Open a browser and navigate to:

```text
http://localhost:8080/sign-in
```

You will see the custom login page, CSS loaded, and a form for username and password. Demo account:

| Username | Demo password | Role |
| --- | --- | --- |
| `an` | `training-pass` | `ROLE_USER` |

**Local use only.** This password is sample data in source code; do not use it in any public environment. Production needs user-chosen/rotated passwords, hashes stored in a controlled store, brute-force protection, and MFA where appropriate.

### 7.1. Checking Before Login

Test in the browser:

- `/sign-in`: returns 200 form, no redirect loop.
- `/public/about`: returns 200 public page.
- `/css/site.css`: returns 200 CSS with a CSS Content-Type.
- `/dashboard`: redirects to `/sign-in` when there is no session.
- `/admin/test`: redirects to login when unauthenticated; when logged in as `an`, rejected because `an` lacks `ROLE_ADMIN`.

You can inspect initial headers/statuses with curl:

```bash
curl -i http://localhost:8080/sign-in
curl -i http://localhost:8080/public/about
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/dashboard
```

**Expected results:** the first three requests return HTTP 200; the last returns an HTTP 302 redirect to `/sign-in`. `curl -i` does not follow redirects unless `-L` is added. In PowerShell, if the `curl` alias behaves differently, use `curl.exe`.

### 7.2. Verifying the CSRF Token in Rendered HTML

Open Developer Tools and inspect the response or `View Page Source` for `GET /sign-in`. With Thymeleaf + Spring Security properly configured, the POST form will include a hidden CSRF token input, usually named `_csrf`.

Illustrative **shape** of the rendered HTML:

```html
<form action="/perform-login" method="post">
    <input name="username" type="text">
    <input name="password" type="password">
    <input type="hidden" name="_csrf" value="...token generated by server...">
    <button type="submit">Sign In</button>
</form>
```

This snippet is **illustrative HTML**, not a usable token. Real tokens vary per session/request and BREACH protection. Never hardcode tokens, copy them from examples into clients, or commit them to source. Thymeleaf automatically integrates `CsrfRequestDataValueProcessor` for POST forms when `th:action` is processed properly.

### 7.3. Valid Login

In the browser, enter `an` / `training-pass` and submit. The browser sends `POST /perform-login` with the appropriate CSRF/session cookie. Spring Security verifies the password, creates the SecurityContext/session, and redirects to `/dashboard` (or the saved request if a protected resource was requested beforehand).

`GET /dashboard` after login shows a greeting for `an`. This is the **expected demo result**. Frameworks may emit different cookie/session headers across containers and environments; do not write brittle assertions over the entire `Set-Cookie` response.

### 7.4. Failed Login

Enter `an` and a password other than `training-pass`. The normal result is HTTP 302 to `/sign-in?error`, after which the login page displays "Invalid credentials." Do not return a specific error like "username exists but password is wrong".

### 7.5. Logout

From the dashboard, click `Sign Out`. The form POSTs to `/sign-out` with the CSRF token; Security's logout handler clears the context/invalidates the session accordingly, then redirects to `/sign-in?logout`.

Then try `/dashboard` again: it redirects back to login. Across multiple devices, logging out of the current session does not automatically revoke sessions on other devices; that is a separate session management/revocation problem.

### 7.6. Sending a POST Without a CSRF Token

```bash
curl -i -X POST \
  -d "username=an&password=training-pass" \
  http://localhost:8080/perform-login
```

With default CSRF, a POST request **without a valid token** normally gets HTTP 403 even when username/password are correct. This is not proof that the POST controller is missing; it is the security filter rejecting a request lacking CSRF. Do not disable CSRF just so cURL returns 302.

To test login manually with a raw HTTP client instead of a browser, the client must GET the login page, preserve cookies/session, extract the real CSRF token from the rendered form, and POST the token + cookie + form fields with proper encoding. Browsers and Thymeleaf handle this naturally; automated tests use Spring Security Test's CSRF support.

## 8. URLs That Need permitAll Beyond the Login Page

### 8.1. CSS, JS, Images, and Favicon

The login page may use:

```text
/sign-in
/css/site.css
/js/login.js
/images/logo.svg
/favicon.ico
```

If they actually exist and are needed by anonymous users, permit them with a narrow matcher:

```java
.requestMatchers(
        "/css/**",
        "/js/**",
        "/images/**",
        "/favicon.ico")
.permitAll()
```

This is a **DSL fragment** that must be placed inside `authorizeHttpRequests` in the right order. Do not permit all of `/assets/**` if unclassified private files live there. Do not put internal documents containing secrets into `src/main/resources/static` just so Thymeleaf can load them.

### 8.2. Public About and Help Pages

`/public/about`, `/public/help`, or terms pages can be public if they expose no account data. A support page requiring login should not be opened merely because "help" appears in the URL; evaluate actual data and actions.

### 8.3. Account Registration

`GET /register` must be reachable if unauthenticated users need to open a signup form. `POST /register` may also not require a logged-in session; however, "public" does not mean the server allows arbitrary roles, skips CAPTCHA/rate limiting, omits email verification, or skips uniqueness checks.

A registration endpoint must validate every input attribute itself. **Never accept `role=ADMIN` from an HTML form and persist it as a server privilege**.

### 8.4. Forgot Password and Password Reset

`GET /forgot-password` is usually public. The email request form can POST to `/forgot-password` without login, but must defend against account enumeration and abuse.

`GET /reset-password?token=...` may be permitted so unauthenticated users can open the reset form. `POST /reset-password` requires an unexpired, unused reset token bound to the right account with proper protections; a reset token is not a login token. For cookie/session browsers, protect with CSRF by design rather than global `csrf.disable()`.

### 8.5. Error Pages and Dispatcher Types

In the Servlet stack, error dispatches can route to `/error`. Spring Security checks authorization across multiple dispatcher types, not only REQUEST. Depending on the app, permitting `DispatcherType.ERROR` and `FORWARD` can help view/error handlers render properly.

**Do not** treat permitting error dispatches as a reason to drop authorization on business URLs for REQUEST. If the app uses multiple servlets/dispatchers or forwards to sensitive endpoints, test specifically rather than broadening rules arbitrarily.

### 8.6. OAuth/OIDC Callbacks If Present

When using OAuth2 Login, callback/authorization-code handling belongs to protocol security filters. Do not blindly write `permitAll("/oauth2/**")` without understanding the endpoints, state/nonce, redirect URIs, and active chain. Custom login HTML can link to `/oauth2/authorization/{registrationId}`, while OAuth2 handles authentication and protocol-level CSRF protection.

## 9. How Does permitAll Differ from web.ignoring?

Both can make a URL look public, yet they are **not equivalent**.

`authorizeHttpRequests(...permitAll())` lets the request **continue through the Spring Security filter chain**. It drops the authentication requirement at authorization while still applying:

- Security headers.
- CSRF protection.
- Session/security context handling.
- Other configured protective filters.
- Security event recording or other chain policies.

`WebSecurityCustomizer.web.ignoring()` excludes a request from the Spring Security filter chain entirely. Using it too broadly for login pages or public POST endpoints can bypass essential defense layers.

For login pages and static assets, the modern recommendation is generally **`permitAll` instead of ignoring**, unless there is a clear technical reason to bypass the filter chain completely. Fixing "CSS returns 302 to login" **does not require** ignoring all of `/css/**`.

Example of the difference:

```text
GET /css/site.css with permitAll:
  -> Passes through Spring Security filters
  -> Does not require Authentication at authorization
  -> Static Resource Handler serves content

GET /css/site.css with ignoring:
  -> Skips SecurityFilterChain
  -> Spring Security filters/headers do not apply there
```

Never use ignoring for `/login` or `/register` as a quick fix for authentication/CSRF misconfiguration without analyzing the consequences.

## 10. URL Variations and Keeping Them Synchronized

You do not have to use `/sign-in` and `/perform-login`. For example, if a team wants the same `/login` path for GET/POST:

```java
.formLogin(form -> form
        .loginPage("/login")
        .loginProcessingUrl("/login")
        .failureUrl("/login?error")
        .permitAll())
```

This is a common, valid configuration: MVC renders GET, while the filter handles POST. However, to clearly learn each responsibility, the main example intentionally separates the two URLs.

If you rename paths, synchronize all of these:

| Component | Example | If mismatched |
| --- | --- | --- |
| `loginPage(...)` | `/sign-in` | Security redirects to URL with no page |
| `@GetMapping(...)` | `/sign-in` | 404 or redirect loop |
| `th:action` | `@{/perform-login}` | POST hits wrong URL |
| `loginProcessingUrl(...)` | `/perform-login` | Filter misses POST |
| `usernameParameter(...)` | `username` | Provider receives empty username |
| `passwordParameter(...)` | `password` | Provider receives empty password |
| `failureUrl(...)` | `/sign-in?error` | Failure redirects to page that doesn't render |
| `logoutUrl(...)` | `/sign-out` | Logout button fails to trigger LogoutFilter |
| `logoutSuccessUrl(...)` | `/sign-in?logout` | Redirects to wrong or non-public path |

Thymeleaf `@{/...}` builds context-path-aware URLs, allowing the app to run under `/app` without hardcoding missing prefixes. When behind a reverse proxy or using `server.servlet.context-path`, verify the base path and forwarded headers; do not concatenate absolute strings outside context resolution.

### Do You Need to permitAll GET /perform-login?

No. In the demo, `POST /perform-login` is what the authentication filter must accept with valid CSRF. `formLogin(...permitAll())` permits the related login URLs; there is no MVC GET page for `/perform-login`. Opening GET on the processing path does not create a login page. **Distinguish authorization rules from the filter's method matcher.**

## 11. Redirect Loops: Causes and Diagnosis

Symptoms: the browser reports "too many redirects", the Network tab repeats `302 /sign-in`, or the response fails to load the form.

### Cause A — Login page is not public

```text
GET /sign-in
  -> AuthenticationEntryPoint
  -> 302 /sign-in
  -> GET /sign-in
  -> ... repeats
```

Solution: ensure the GET login page has `permitAll` and form login has `permitAll()`. Check which rule matches **first**, especially with `anyRequest().authenticated()`.

### Cause B — Another SecurityFilterChain intercepts the URL

Suppose the app has an `@Order(1)` chain on `/**` requiring authentication, while public form login is configured in an `@Order(2)` chain. The first chain can catch `/sign-in`, preventing the lower chain from ever running.

Solution: inspect `securityMatcher` and `SecurityFilterChain` ordering, and test that login/processing URLs hit the right chain. Do not inspect only one config bean and assume the whole app behaves accordingly.

### Cause C — MVC route does not exist

`loginPage("/sign-in")` only sets the URL; it does not generate a controller. Missing `@GetMapping("/sign-in")` or a wrong template path can yield 404/error responses instead of a login form.

### Cause D — Session/cookie is not preserved

A valid login may 302 to dashboard, yet the browser gets bounced back to login because the session cookie is not saved/sent (Secure, SameSite, domain, path, reverse proxy, HTTP/HTTPS mismatch) or the app accidentally configured `SessionCreationPolicy.STATELESS`.

### Cause E — Login processing fails to match

If the form submits to a URL different from `loginProcessingUrl`, the POST is not handled by the authentication filter; errors are typically 404, 405, 403 CSRF, or unexpected redirects.

### Cause F — Misconfigured saved request or success URL

If the success handler always redirects to a URL that triggers another redirect flow, a loop can occur. Check the saved request cache, `defaultSuccessUrl`, proxy redirects, and rules on the target.

### Systematic Debugging Steps

1. Open Developer Tools → Network and enable Preserve log.
2. Trace the sequence `GET /dashboard` → `302 /sign-in` → `GET /sign-in`.
3. Check whether `/sign-in` returns HTTP 200 or another 302.
4. Verify the HTML response actually contains the form and CSS does not redirect to login.
5. On submit, check whether `POST /perform-login` includes the CSRF cookie/hidden token, and check its status and `Location`.
6. Check whether the browser sends back the session cookie on the post-login request.
7. With multiple filter chains, check DEBUG logs for which chain matched.
8. Never enable logging of raw passwords, session cookies, or CSRF tokens in production to debug.

## 12. CSRF: permitAll Does Not Disable POST Verification

A common misconception: "`POST /perform-login` must be public, so CSRF must be turned off." This is false.

- **Authorization:** a login request has no authenticated user yet, so the login processing endpoint cannot require prior authentication.
- **CSRF:** a browser can be tricked by an external site into submitting a form on a user's behalf. CSRF protection blocks state-changing requests that did not originate from a valid form.

Therefore, `permitAll` for login does not remove `CsrfFilter`. Spring Security protects login POST and logout POST by default.

### Role of Thymeleaf

Thymeleaf integrates with `RequestDataValueProcessor` in Spring MVC/Security. Using `th:action` on a POST form normally injects the hidden CSRF input. When viewing rendered HTML, you should see an input typically named `_csrf` with a valid token value.

**Never** copy static HTML with a fixed CSRF token. Tokens must be tied to the session/request strategy and verified server-side. If building a frontend without Thymeleaf, obtain and attach the CSRF token over a secure channel on POST requests.

### Why Does POST via curl Return 403?

A request like:

```bash
curl -i -X POST -d "username=an&password=training-pass" \
  http://localhost:8080/perform-login
```

typically gets 403 if it lacks a valid CSRF token, even with the right password. This is a useful test proving that `permitAll` does not mean "drop all protections".

### Tokens After Login/Logout

Spring Security may rotate/clear the CSRF token upon authentication or logout. An AJAX frontend reusing a stale CSRF token after login can hit 403 on the next operation. For SPAs or AJAX, implement proper token refresh after login/logout instead of disabling CSRF as a workaround.

## 13. Public Routes and Actual Risk Levels

| URL type | Can be public? | Other protections needed |
| --- | --- | --- |
| GET login page | Yes | CSP/HTTPS, no caching of sensitive info |
| Login POST | No prior login required | CSRF, rate limiting, credential validation, audit |
| GET register page | Yes | Do not expose internal data |
| Register POST | Depends on business rules | CSRF, email verification, anti-spam, uniqueness |
| Forgot password GET/POST | Possible | Generic responses against user enumeration, rate limits |
| Reset password GET/POST | Possible | Single-use token, expiry, account binding, CSRF policy |
| Static login CSS/logo/JS | Yes | Control content and origin |
| Public docs/terms | Yes | No leakage of internal docs |
| Profile/me | No | Authenticated and owner checks |
| Account settings/change password | No | Authentication, reauth/MFA as needed, CSRF |
| Admin | No | Admin role and resource authorization |
| Actuator/metrics | Usually no | Dedicated operational access control |
| Error dispatch | Often permitted | Prevent error pages from leaking stack traces/secrets |

**Do not infer harmlessness from URL names.** An endpoint starting with `/public/` that dumps all user emails is still a design vulnerability. Public routes only describe auth requirements; response content and business logic still require security review.

### Avoiding User Enumeration

Login failure pages should show a generic message like "Invalid credentials." rather than distinguishing "account does not exist" from "wrong password". Similarly, `/forgot-password` should respond neutrally so registered email addresses are not disclosed, alongside rate limiting to prevent abuse.

## 14. HTTP 302, 401, 403, and 404 on Form Login

Commonly observed status codes:

| Scenario | Typical result | Notes |
| --- | --- | --- |
| Anonymous GET `/sign-in` | 200 | Public login page |
| Anonymous GET `/dashboard` | 302 → sign-in | Browser form login |
| Form login wrong credentials, valid CSRF | 302 → `/sign-in?error` | Failure handler |
| Form login valid credentials, valid CSRF | 302 → saved URL/dashboard | Success handler |
| POST login missing CSRF | 403 | CsrfFilter rejects before authentication |
| Authenticated, missing `ROLE_ADMIN` | 403 | Authorization |
| CSS blocked by security | May 302 → login | Browser sees broken CSS / HTML instead of CSS |
| Missing GET login controller | 404 or error flow | `loginPage` does not generate MVC routes |
| Processing URL receives wrong method/path | 404/405/403 or other route | Depends on matcher/filter/controller |
| Basic/Bearer API without credentials | Usually 401 | Different from form-login redirect UX |

Do not write tests asserting that every authentication error returns 401 when the app uses form login; 302 redirects are normal browser-oriented behavior. If an app serves both APIs and pages, separate entry points/chains by traffic type.

## 15. End-to-End Testing for Login Pages and Public URLs

Testing only that the `GET /sign-in` controller returns a view name is insufficient; tests must traverse the **Spring Security filter chain** with session/CSRF.

### Test Matrix

| Test | Input | Key assertion |
| --- | --- | --- |
| Anonymous GET login | `GET /sign-in` | HTTP 200, HTML contains form |
| Login failure page | `GET /sign-in?error` | HTTP 200, generic message |
| Public about | `GET /public/about` | HTTP 200 |
| Public CSS | `GET /css/site.css` | HTTP 200, CSS body |
| Anonymous dashboard | `GET /dashboard` | 302 to `/sign-in` |
| Login processing POST | valid username/password + CSRF | Filter handles, 302 after auth |
| Wrong credentials | wrong username/password + CSRF | 302 to `/sign-in?error` |
| POST missing CSRF | username/password only | 403 |
| Dashboard after login | Valid session cookie | 200, matching principal name |
| Logout POST | Cookie + valid CSRF | 302 `/sign-in?logout`, session cleared |
| Dashboard after logout | Old cookie | 302 back to login |
| Admin route with `ROLE_USER` | Log in as `an` then GET `/admin/**` | 403 if endpoint is mapped |
| Login page with CSS | Browser loads link from HTML | CSS does not redirect to login |
| Duplicate security chains | Multiple `@Order`/`securityMatcher` | Login belongs to expected chain |
| Non-root context path | Deployed under `/app` | Thymeleaf URLs keep context path |
| CSRF token after login/logout | Use new token | Next POST does not unexpectedly 403 |
| Session fixation | New login | Session ID handled per policy |
| Open redirect | Strange redirect URL input | Never redirects to untrusted domain |
| Forgot/reset if present | Public pages & POST | Token verification and separate rate limit |

### Testing with Spring Security Test and MockMvc

When building real project tests, use `MockMvc` with Spring Security Test. Below is a **reference snippet**, not a complete test file (requires imports, test annotations, and test starters matching your Spring Boot version):

```java
mockMvc.perform(get("/sign-in"))
        .andExpect(status().isOk());

mockMvc.perform(get("/dashboard"))
        .andExpect(status().is3xxRedirection());

mockMvc.perform(post("/perform-login")
        .param("username", "an")
        .param("password", "training-pass")
        .with(csrf()))
        .andExpect(status().is3xxRedirection());

mockMvc.perform(post("/perform-login")
        .param("username", "an")
        .param("password", "training-pass"))
        .andExpect(status().isForbidden());
```

`get`/`post` come from `MockMvcRequestBuilders`, `status` from `MockMvcResultMatchers`, and `csrf` from `SecurityMockMvcRequestPostProcessors`. In Boot 4, test dependencies are modularized; choose the MVC/Security test starters managed by Boot rather than blindly copying old coordinates.

For login/session tests, you may need to pass the same `MockHttpSession` into follow-up requests; do not run two independent `mockMvc.perform` calls assuming they share cookies automatically.

### Browser Checks Beyond curl

A realistic flow:

1. Open `/dashboard` in an incognito window.
2. Verify redirect to `/sign-in`.
3. Verify HTML, CSS, and CSRF token load without prior login.
4. Enter a wrong password and verify the generic failure message.
5. Enter `an`/`training-pass`, verify the target URL and dashboard.
6. Open a new tab, visit `/dashboard`, and verify the session persists.
7. Click logout; retry dashboard and verify access is revoked.
8. Open the Network tab to confirm static assets never redirect to sign-in.
9. Check cookie flags `Secure`/`HttpOnly`/`SameSite` and HTTPS for the deployment environment.

## 16. Sessions, Cookies, Reverse Proxies, and Real Environments

If a login page is public yet logging in sends the user right back to login, the session may not be sticking:

- Reverse proxy terminates TLS but app sees the wrong forwarded scheme, looping `http://` ↔ `https://`.
- Cookie domain/path mismatches the host/context path.
- `Secure` cookie is not sent over plain HTTP or browser blocks third-party cookies.
- App configured `SessionCreationPolicy.STATELESS` when browser sessions were intended.
- Session store lives on one node while the next request hits another node without shared state.
- Login success handler redirects to the wrong host/domain or unintended URL.
- CSRF token belongs to another session because the client dropped cookies between GET and POST.

Spring Security protects against session fixation in the standard flow; do not casually disable session management or manually create a session and copy SecurityContext while bypassing security strategies. For load-balanced browser apps, use a shared session store or well-scoped affinity.

### Avoid Dangerous Session Fixation Workarounds

Upon successful login, the session ID may rotate to prevent session fixation. This is intentional. If a test client pins the old session cookie and treats login as failing, fix how the client stores `Set-Cookie` and sends the new cookie; never disable session fixation protection just to make a test pass.

### HTTPS, Cookies, and Caching

Both the login page and credential POST require HTTPS—not just production data endpoints. Session cookies need appropriate flags. Never cache responses containing authentication state or CSRF tokens in shared proxies. Caching static CSS can be helpful, provided no tokens or PII leak into public assets.

## 17. Multiple SecurityFilterChains in the Same Application

Consider a system with both browser pages and a REST API:

```text
SecurityFilterChain #1: /api/**
    -> Bearer token / HTTP Basic depending on protocol
    -> stateless, typically returns 401 for API

SecurityFilterChain #2: browser MVC pages
    -> custom formLogin /sign-in
    -> session-based, 302 redirect to login
```

Key questions:

- Which chain matches `GET /sign-in`?
- Which chain matches `POST /perform-login`?
- Which chain matches static `/css/**`, `/images/**`?
- Is the login URL captured early by a broad `/**` chain?
- Do CSRF and CORS differ between API and browser?
- Which logout handler and entry point apply to each chain?

**Only the first matching chain runs.** If the form-login processing URL falls outside the `securityMatcher` of the chain containing `formLogin`, POST will not be handled by `UsernamePasswordAuthenticationFilter`. If a Bearer API chain captures `/sign-in`, browsers may receive a 401 JSON error instead of the login page.

When defining multiple chains, declare `securityMatcher`/`@Order` explicitly, test every public URL, and ensure static/login routes land in the right chain. Never put `anyRequest().permitAll()` into a catch-all chain to mask ordering bugs.

## 18. Common Mistakes

| Mistake | Symptom/risk | Fix |
| --- | --- | --- |
| Custom `loginPage` without MVC GET mapping | 404 / no form displayed | Add `@GetMapping` and template |
| Login page not permitted | Redirect loop | Form `permitAll()` and public GET login rule |
| Login page public but CSS not public | CSS gets HTML/302 | Permit the static paths properly |
| Form action differs from processing URL | 404/405/login doesn't run | Align `th:action` and `loginProcessingUrl` |
| Assuming POST controller is auth provider | Bypasses security pipeline | Let `UsernamePasswordAuthenticationFilter` handle it |
| Input named `email` without updating `usernameParameter` | Login fails | Synchronize parameter names |
| Sending password via GET | Exposed in URLs/logs | POST + HTTPS |
| Dropping CSRF because login POST is public | Login CSRF / session abuse | Keep CSRF + hidden token |
| Using `permitAll("/**")` to fix login loop | Exposes all resources | Narrow public matchers |
| Using `web.ignoring("/**")` | Skips all security filters | Use `permitAll` for public paths |
| Forgetting `?error`/`?logout` display | Confusing UX | Template reads query parameters |
| Showing "username does not exist" | User enumeration | Generic message and rate limiting |
| Logout via GET with CSRF enabled | Not processed / broken logout | POST logout form |
| Public reset endpoint ignores reset token | Account takeover | Single-use token, TTL, verification |
| Trusting client-submitted register role | Privilege escalation | Assign roles via server policy |
| Broad API chain placed before login chain | Login gets wrong 401/redirect | Review `securityMatcher` and ordering |
| Enabling `STATELESS` for form sessions | Login forgotten immediately | Use appropriate session policy |
| Reverse proxy misconfigures scheme | HTTP/HTTPS redirect loop | Forwarded headers and cookie flags |
| Ignoring ERROR dispatch | Errors turn into access denied | Configure dispatcher types properly |
| Testing controller without filter chain | False confidence | MockMvc + Spring Security integration |
| Using demo passwords in production | Credential compromise | Proper account store and secret policy |
| Skipping anonymous GET login tests | Redirect loop reaches production | Integration test public routes |

## 19. Self-Check Questions

**Q1.** Does `loginPage("/sign-in")` automatically generate an MVC controller or Thymeleaf file?  
**Answer:** No. The application must provide the GET handler/template; Spring Security only needs the URL to redirect to and coordinate form login.

**Q2.** Why must `GET /sign-in` be accessible without an `Authentication`?  
**Answer:** Because users must see the form before submitting credentials. If the login page itself requires login, a redirect loop can occur.

**Q3.** Where is `POST /perform-login` handled?  
**Answer:** Inside `UsernamePasswordAuthenticationFilter` when URL/method match the configuration; no separate POST controller is needed.

**Q4.** Does `formLogin(...permitAll())` automatically open `/css/site.css`?  
**Answer:** No. Static assets need their own matching public rules.

**Q5.** Why doesn't `permitAll` disable CSRF?  
**Answer:** Because it only governs authorization decisions, while `CsrfFilter` continues protecting unsafe methods like login/logout POSTs.

**Q6.** If a POST has the right password but lacks `_csrf`, what usually happens?  
**Answer:** The request is blocked with 403 due to CSRF before password authentication runs.

**Q7.** How does Thymeleaf help submit the CSRF token?  
**Answer:** When using `th:action` on a POST form with proper Spring MVC/Security integration, `RequestDataValueProcessor` inserts the hidden CSRF input.

**Q8.** The login page renders, but CSS redirects to login. Where is the fix?  
**Answer:** Check the actual static path and the `permitAll` rule for CSS—do not open all URLs or disable security.

**Q9.** Why shouldn't you write `@PostMapping("/perform-login")` to verify passwords manually?  
**Answer:** Because the filter, manager/provider, and security strategies already exist; manual code easily conflicts with them or omits protections.

**Q10.** Should `/admin/**` be permitted so the login page loads faster?  
**Answer:** No. Only login/assets are public; admin routes still require admin privileges.

**Q11.** When does `defaultSuccessUrl("/dashboard", false)` not send the user straight to dashboard?  
**Answer:** When Spring Security holds a valid saved request (e.g., the user visited a protected page before logging in) and the success handler prioritizes it.

**Q12.** Does logout via `POST /sign-out` require CSRF?  
**Answer:** In a browser session flow with default CSRF, yes; a Thymeleaf POST form can insert the token automatically.

**Q13.** How does `permitAll` differ from `web.ignoring`?  
**Answer:** `permitAll` still passes through `SecurityFilterChain`; ignoring bypasses the chain entirely, potentially dropping security headers/CSRF/filter protections.

**Q14.** With two `SecurityFilterChain` beans, which one runs?  
**Answer:** The first chain whose matcher matches the request. Make sure the login page/processing URLs fall inside the chain with the right form-login config.

**Q15.** Login succeeds, yet navigating to dashboard redirects back to login. What should you check?  
**Answer:** Session cookie, Secure/SameSite/path/domain, session policy, reverse proxy, multi-node store, success URL, and actual HTTP requests.

## 20. Pre-Deployment Practical Checklist

1. Explicitly list public paths: login GET, failure/logout landing page, CSS/JS/logo, public content, and signup/forgot/reset if present.
2. Distinguish `loginPage` and `loginProcessingUrl`; the form POST action must match the filter.
3. Configure `formLogin(...permitAll())` and narrow public matchers; keep remaining URLs `authenticated()/hasRole` per policy.
4. Create the GET login controller and real template; do not write a duplicate POST password-checking controller alongside the filter.
5. Use `th:action` so Thymeleaf integrates the CSRF token into POSTs; inspect rendered HTML.
6. Keep CSRF enabled for browser sessions; do not disable it just for simple cURL POSTs.
7. Verify public assets return HTTP 200 with the right MIME type rather than redirects/HTML when loading CSS.
8. Do not leave admin/profile/account endpoints public just because their names resemble help pages.
9. If register/forgot/reset exist, protect against spam, enumeration, reset-token replay, and CSRF per threat model.
10. Enforce HTTPS, password hashing, rate limiting/MFA as needed, session cookie flags, and session fixation protection.
11. Test anonymous GET login, protected redirects, login success/failure, CSRF 403, POST logout, and anonymous assets.
12. Review ordering of multiple `SecurityFilterChain`s, servlet context matchers, ERROR/FORWARD dispatchers, and reverse proxies.
13. Never use broad `web.ignoring` or `anyRequest().permitAll()` to paper over bugs.
14. Never log raw passwords, CSRF tokens, session cookies, or credential header contents.
15. Use a real account store and user management policy in production; never keep demo passwords.
16. Monitor current Spring Boot/Spring Security advisories/versions and run regression tests.

## Conclusion

A custom login page needs **a public GET endpoint to render the form**, **a POST authentication processing URL handled by Spring Security**, and **the static/public resources genuinely needed by anonymous users to load the page**. The two login URLs serve distinct purposes; `permitAll` only removes the authentication requirement during authorization without disabling CSRF or other protections.

In Spring Security Servlet, `loginPage`, `loginProcessingUrl`, `failureUrl`, `defaultSuccessUrl`, and `permitAll` must align with your controllers/templates, static asset paths, and `anyRequest().authenticated()` rules. Using Thymeleaf helps attach CSRF tokens to POST forms; test real browser/session flows and the active filter chain to avoid redirect loops, 403 missing-token errors, and CSS redirected to the login page.

**Remember:** *The login page and the assets needed to display it must be public. The credential-checking endpoint cannot require prior login, yet it must still be protected by CSRF and the authentication pipeline. All remaining business resources require proper authorization.*

### Official References

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF in Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
