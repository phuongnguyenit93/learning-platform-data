# Static Resources, Error Pages, and Login Endpoints Also Must Be Considered

## 1. Why Does Endpoint Protection Involve More Than Business APIs?

When enabling Spring Security for a web application, we often focus on APIs like **/account/**, **/orders/**, or **/admin/**. Yet a request flow for a user to actually use the application may also need:

- Loading static resources: CSS, JavaScript, images, favicon.
- Opening the login page and submitting authentication credentials.
- Viewing login failure messages, logout confirmation, or an access-denied page.
- Seeing a meaningful error page when a URL does not exist or the server encounters an error.
- Accessing URLs forwarded internally through the servlet dispatcher mechanism.

If you apply a blanket rule such as **anyRequest().authenticated()** without thinking about the paths supporting login, an unauthenticated user may be redirected to the login page while the CSS and images for that page are also protected. If a custom login page is not permitted, redirects can form a loop or render broken pages. If a server-side error is dispatched to **/error** while error dispatches require authentication, users may see a login prompt/403 instead of the original error.

Lesson goal: **account thoroughly for supporting request groups when designing policies**, distinguish normal HTTP requests from ERROR/FORWARD dispatches, understand exact permissions for the login page, and place narrow exceptions before catch-all rules protecting the rest.

> Technical scope: the primary examples use **Spring Boot 3.x, Spring MVC/Servlet, Spring Security 6.x, Java 17+**. In Spring WebFlux, the principles are equivalent, though the reactive configuration API differs; do not use Servlet FilterChain/HttpSecurity in a pure WebFlux application.

## 2. Which Paths Does a Website Need?

Consider an internal management website with a login page, a profile page, and an admin area:

| Group | Example request | Suggested rule | Reason |
| --- | --- | --- | --- |
| Public static resources | GET /css/site.css, /js/app.js, /images/logo.png | **permitAll()** for chosen public locations | Browser needs to load UI assets before login |
| Login page | GET /login | **permitAll()** | Unauthenticated users must see the form |
| Login processing | POST /login | Allow Spring Security to process credentials; configure formLogin(...).permitAll() | Unauthenticated users must be able to submit the form |
| Login error message | GET /login?error | Matches GET /login | Query parameter is not a separate protected URL |
| Public page | GET /about | **permitAll()** if intentionally public | Non-sensitive content |
| Profile page | GET /private | **authenticated()** | Logged-in users only |
| Admin area | GET /admin | **hasRole("ADMIN")** | Requires **ROLE_ADMIN** authority by default |
| Servlet ERROR dispatch | Dispatch to /error | Can be **permitAll** for DispatcherType.ERROR | Allows rendering original errors without prompting login again |
| Access-denied page | Page shown after 403, if custom-built | Explicitly decide GET permission and error/forward mechanism | Prevents loops when unauthorized users need to read the message |
| Other URLs | /internal/..., unexpected methods | **denyAll()** or another explicit policy | Avoids accidentally exposing new endpoints |

This is a policy example. Not every static file should be public: user-exported documents, private attachments, and tenant data must **not** be placed in a public static folder just for fast downloads.

**permitAll does not mean "skip Spring Security."** It only permits at the authorization step; other security layers in the filter chain can still process the request.

## 3. Static Resources: Real URL Differs from File Location on Disk

With Spring Boot MVC and default static configuration, common files can be served from classpath locations such as:

~~~text
src/main/resources/static/css/site.css
src/main/resources/static/js/app.js
src/main/resources/static/images/logo.png
~~~

The corresponding URLs are usually:

~~~text
GET /css/site.css
GET /js/app.js
GET /images/logo.png
~~~

**Do not prepend /static to the URL.** The **static** folder is where Spring Boot looks for resources, not necessarily part of the request path. If the application has changed **spring.mvc.static-path-pattern**, resource handler configuration, or context path, verify the real URL instead of guessing from the file tree.

### 3.1. Configuring `permitAll` by Specific Paths

Fragment in Spring Security Servlet configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**", "/images/**")
            .permitAll()
        .anyRequest().authenticated());
~~~

This pattern is simple when the application tightly controls those paths. However, it has two limits: forgetting a new folder like **/webjars/** can break UI assets; using an overly broad matcher like **/*** will expose sensitive URLs.

Spring Boot also provides a convenient matcher:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Inside authorizeHttpRequests:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
~~~

**PathRequest.toStaticResources().atCommonLocations()** matches the common static resource locations known to Spring Boot. This is a **Spring Boot Servlet** API, not a Spring Security core method. If a project uses custom locations, inspect the actual matcher and add appropriate rules.

### 3.2. `permitAll` Differs from `web.ignoring`

These two approaches yield very different results:

| Approach | Does the resource go through Spring Security FilterChainProxy? | Effect |
| --- | --- | --- |
| **requestMatchers("/css/**").permitAll()** | Yes | Permits authorization, while related security filters—including security headers—still have a chance to run. |
| **WebSecurityCustomizer / web.ignoring()** | No, for ignored URLs | Bypasses the entire Spring Security filter chain for that URL; headers from Spring Security will not be added by this chain. |

In modern Spring Security, the recommended approach is usually **permitAll for static assets** instead of ignoring the filter chain. Do not use ignoring just because "static files are unrelated to security." For resources that must be protected, apply an appropriate policy rather than putting them in an ignored zone.

### 3.3. Which Files Should Be Public?

- **Usually public:** CSS/JS for the login page, logos, general UI images, public fonts, favicon.
- **Usually require control:** personal PDFs, private reports, unapproved user photos, attachments, tenant-scoped data, downloads containing sensitive information.
- **Should not be served as static:** internal configuration, secrets, private keys, unreleased source code, or data requiring ownership checks.

Allowing **/images/** does not make every resource inside automatically safe; verify that the folder **contains only content fit for public access**. If downloadable content needs protection, serve it through an endpoint or delivery mechanism with authorization and per-resource permission checks.

## 4. The Login Page Is Part of the Security Flow

### 4.1. `GET /login` and `POST /login` Have Two Roles

When using form login with a custom login page:

~~~text
Unauthenticated user -> GET /private
                           |
                           v
                   Not authenticated
                           |
                           v
                   Redirect 302 -> GET /login
                                      |
                                      +--> Public HTML + CSS/JS
                                      |
                                      +--> User enters credentials
                                      |
                                      v
                                  POST /login
                                      |
                                      +--> Form authentication filter verifies
                                             |
                                             +--> Success: saves SecurityContext per config,
                                             |             redirects to target page
                                             |
                                             +--> Failure: redirects to /login?error
~~~

- **GET /login** is typically served by an MVC Controller or template engine, returning HTML.
- **POST /login** in default form login is the **authentication-processing route handled by Spring Security's filter**. You do not need to add a custom @PostMapping("/login") just to validate username/password in this example.
- **loginPage("/login")** specifies the form page; **loginProcessingUrl("/login")** specifies the URL receiving credentials.
- **formLogin(...).permitAll()** ensures routes supporting login are permitted according to configuration, such as the login page and form submission URL.
- **failureUrl("/login?error")** is where users are sent when credentials are wrong. The URL path is still **/login**; the **?error** part does not alter path matching.

A login page is not automatically secure just because it has `permitAll`: POST login must be authenticated properly by Spring Security, HTTPS is needed in production, cookies/sessions must be configured properly, and the application must preserve CSRF protection on the form.

### 4.2. Generated Login Page vs. Custom Login Page

If you use **formLogin(Customizer.withDefaults())** without setting a custom page, Spring Security can generate a default login page for development. When using **loginPage("/login")**, **the application must actually serve GET /login**, for instance via an MVC Controller returning the **login** template. Adding `loginPage` config without a handler/template can cause login requests to end in 404 or confusing redirect loops.

Related URLs such as **/login?error** and **/login?logout** should be checked in real tests, since users see them when authentication fails or logout succeeds.

## 5. Error Pages and `DispatcherType`: Same URL Does Not Guarantee Same Context

The Servlet API has several dispatch types, the most relevant here being:

| DispatcherType | Common meaning | Example |
| --- | --- | --- |
| **REQUEST** | Initial request from client | Browser sends GET /private |
| **ERROR** | Server/container dispatches to handle an error | An exception leads to error handling at /error |
| **FORWARD** | Request internally forwarded to another resource | Controller forwards to a view or handler |
| **ASYNC** | Asynchronous processing requiring another dispatch | Servlet async processing |

An external **GET /error** and an internal **ERROR dispatch to /error** are not the same: the same URL can carry different `DispatcherType`s. If a project applies authorization rules across dispatcher types, an original request that already passed permission checks can face a second check while rendering an error.

Spring Security supports matching by dispatcher type:

~~~java
import jakarta.servlet.DispatcherType;

// Inside authorizeHttpRequests configuration:
.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
~~~

This rule allows only **ERROR dispatches**, not **every direct REQUEST to /error** by default. It expresses intent far more clearly than permitting all path calls to **/error**. Depending on the application, allowing error dispatches helps preserve the original 404/500 status or error page.

Spring Security documentation also illustrates allowing **DispatcherType.FORWARD, DispatcherType.ERROR** when view-rendering architectures need those forwards. However, **do not blindly open all FORWARDs**: if the application performs internal forwards to sensitive handlers, review paths and authorization enforcement points to avoid creating unintended access routes.

### 5.1. Does a 403 Error Always Go Through `/error`?

No. **403** can come from authorization, CSRF, access-denied handling, or be returned directly by an application component. Depending on **AccessDeniedHandler**, exception handling, and container configuration, responses can be written directly or dispatched to an error view. **/error** usually ties into Spring Boot MVC's error-handling infrastructure; do not treat it as the sole handler for every error status.

Nor can you assume a non-existent URL always returns 404. If `SecurityFilterChain` rejects the request **before MVC looks up a handler**, the response can be 302 to login, 401, or 403 depending on the authentication mechanism. To test a public 404 page, you need a path permitted by authorization that has no actual resource/controller.

### 5.2. Custom Error Pages Must Be Safe

If an application builds custom error pages, such as **templates/error/404.html** or **templates/error/500.html** in a template-engine Boot app, display user-friendly information:

- Do not expose stack traces, SQL details, filesystem paths, or tokens.
- Do not depend on static assets that only logged-in users can load.
- Do not turn an error path into a secret data lookup API.
- Distinguish **messages users are allowed to see** from **error details meant for internal logging**.

Allowing an error message to render does not mean granting access to protected data or treating the original business action as successful.

## 6. Complete Demo: Spring Boot 3, Public CSS, Form Login, and ERROR Dispatch

This example shows three flows inside one application:

1. An unauthenticated user can load **/login** and **/css/site.css**.
2. An unauthenticated user is redirected when accessing **/private**, while a user with ROLE_USER can access it after logging in.
3. An error triggered by public request **/broken** is handled as HTTP 500; allowing ERROR dispatches does not turn an error into success.

### 6.1. Create the Project and Files

Use **Spring Initializr** to create a **Gradle**, **Java 17+**, **Spring Boot 3.x** project, group **com.example**, artifact **demo**. Select dependencies:

- **Spring Web** (spring-boot-starter-web)
- **Spring Security** (spring-boot-starter-security)
- **Thymeleaf** (spring-boot-starter-thymeleaf)

Create these three files:

~~~text
src/main/java/com/example/demo/SecurityAssetsApplication.java
src/main/resources/templates/login.html
src/main/resources/static/css/site.css
~~~

Keep the build/config files generated by Spring Initializr intact. You do not need to write a new authentication filter; Spring Security already provides form-login handling.

### 6.2. Java: `SecurityAssetsApplication.java`

Place the **entire** code below in **src/main/java/com/example/demo/SecurityAssetsApplication.java**:

~~~java
package com.example.demo;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@SpringBootApplication
public class SecurityAssetsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityAssetsApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Allow internal dispatch when rendering errors.
                .dispatcherTypeMatchers(DispatcherType.ERROR)
                    .permitAll()

                // Common CSS, JS, images, and static resources.
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations())
                    .permitAll()

                // Login page, public page, and error-testing endpoint.
                .requestMatchers(HttpMethod.GET,
                    "/login", "/hello", "/broken")
                    .permitAll()

                // POST /login is handled by the form-login filter.
                .requestMatchers(HttpMethod.POST, "/login")
                    .permitAll()

                // Internal area requires authentication only.
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()

                // Admin area requires ROLE_ADMIN.
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")

                // Deny all other URLs/methods by default.
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/private", true)
                .failureUrl("/login?error")
                .permitAll()
            );

        // CSRF remains enabled by default, including for POST /login.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails member = User.withUsername("member")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}

@Controller
class DemoPages {

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @ResponseBody
    @GetMapping("/hello")
    String publicPage() {
        return "public";
    }

    @ResponseBody
    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "hello-" + authentication.getName();
    }

    @ResponseBody
    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }

    @ResponseBody
    @GetMapping("/broken")
    String broken() {
        throw new IllegalStateException("demo-error");
    }
}
~~~

**Configuration explanation:**

- The **DispatcherType.ERROR** matcher handles error dispatches accurately. Original `REQUEST`s still go through the remaining rules.
- **PathRequest** allows common static assets in Spring Boot. Resources still traverse the filter chain, giving Spring Security–managed security headers a chance to be added to responses.
- **GET /login** is rendered as a template by the MVC Controller; **POST /login** is handled by Spring Security. There is no `@PostMapping("/login")` manually validating passwords.
- **authenticated()** requires login on GET /private.
- **hasRole("ADMIN")** by default requires authority **ROLE_ADMIN**, produced by `roles("ADMIN")` on `UserBuilder`.
- **anyRequest().denyAll()** prevents unlisted endpoints or HTTP methods from becoming public automatically.
- CSRF is not disabled. **{noop}demo123** is for local demo only; real systems must use a `PasswordEncoder` and proper user store.

### 6.3. HTML: `templates/login.html`

Put the following contents in **src/main/resources/templates/login.html**:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign in</title>
    <link rel="stylesheet" th:href="@{/css/site.css}">
</head>
<body>
<main class="login-card">
    <h1>Sign in</h1>
    <p>Use member or admin; password demo123.</p>

    <form th:action="@{/login}" method="post">
        <label for="username">Username</label>
        <input id="username" name="username" autocomplete="username"
               required>

        <label for="password">Password</label>
        <input id="password" name="password" type="password"
               autocomplete="current-password" required>

        <button type="submit">Sign in</button>
    </form>
</main>
</body>
</html>
~~~

In a **Thymeleaf + Spring MVC/Spring Security** setup, a form using **th:action** for POST is processed through **RequestDataValueProcessor** and gets a CSRF token inserted into the rendered HTML. The template above uses the default field names **username** and **password**, posting to **/login**. You can inspect the rendered HTML in DevTools to verify the hidden CSRF field appears. If using another template engine or custom form mechanism, you must actively send the CSRF token as required by the application.

The path **src/main/resources/templates/login.html** is where Thymeleaf looks for templates, **not** a public static resource at URL /templates/login.html. Users access it via **GET /login** routed by the controller.

### 6.4. CSS: `static/css/site.css`

Put the following contents in **src/main/resources/static/css/site.css**:

~~~css
body {
    font-family: Arial, sans-serif;
    background: #f4f6fb;
    margin: 0;
    padding: 40px 16px;
}
.login-card {
    max-width: 360px;
    margin: 0 auto;
    padding: 24px;
    background: white;
    border-radius: 10px;
    box-shadow: 0 5px 25px rgba(0, 0, 0, 0.08);
}
label {
    display: block;
    margin-top: 14px;
}
input, button {
    display: block;
    box-sizing: border-box;
    width: 100%;
    padding: 10px;
    margin-top: 6px;
}
button {
    margin-top: 20px;
    cursor: pointer;
}
~~~

This CSS file is served by Boot at **GET /css/site.css**. It requires no login thanks to the static matcher. If CSS on the login page fails to load, open the URL `/css/site.css` directly in a private browser window and check the status, response content type, context path, and matching security rule.

### 6.5. Running

In the Gradle project root:

~~~bash
./gradlew bootRun
~~~

On Windows use **gradlew.bat bootRun**. By default the application listens on **http://localhost:8080** unless the port setting was changed.

Before logging in, test in a browser:

1. Open **http://localhost:8080/login**: the form displays with CSS.
2. Open **http://localhost:8080/css/site.css**: 200 response with CSS content.
3. Open **http://localhost:8080/private**: browser is redirected to `/login`.
4. Log in with **member / demo123**: browser is sent to **/private**, returning **hello-member**.
5. Open **/admin** while logged in as member: denied 403 due to missing `ROLE_ADMIN`.
6. Log in in a new session as **admin / demo123**: can open **/admin** and receive **admin**.
7. Open **/broken**: controller intentionally throws an exception; response normally has status 500 and is handled by Spring Boot error handling.

With curl, you can observe **GET** requests without a CSRF token:

~~~bash
curl -i http://localhost:8080/login
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/private
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/broken
~~~

**Expected HTTP results from configuration**, not an actual run log:

| Unauthenticated request | Expected status | Why |
| --- | --- | --- |
| GET /login | **200** | Permitted via `permitAll` and has template |
| GET /css/site.css | **200** | Belongs to permitted static group |
| GET /hello | **200** | Public endpoint |
| GET /private | **302** | Form-login entry point redirects to /login |
| GET /admin | **302** | No Authentication yet; sent to /login |
| GET /broken | **500** | Controller throws exception; error handler preserves status |
| GET /css/missing.css | **404** (for non-existent resource) | Static path is permitted to proceed to MVC to report not found |

If requests pass through a reverse proxy, a different context path, custom error handlers, or different settings, specific URLs/statuses/headers may differ. With curl not following redirects automatically without **-L**, you will see **302** and the `Location` header.

### 6.6. Note When Testing `POST /login` with curl

Because **CSRF is enabled**, sending `POST /login` directly via curl **without a matching token and session** can return 403 *before* authentication even checks the password. To test login like a browser, you must:

1. Send `GET /login` to obtain the session cookie and CSRF token from the form.
2. Send `POST /login` with that same session cookie, the **username** and **password** fields, and the corresponding CSRF token.
3. Observe the success redirect to `/private` or failure redirect to `/login?error`.

In a browser, the example's Thymeleaf form already handles including the token in the request. This is why the example **does not disable CSRF just to make curl POST convenient**. For projects using another authentication style, token/cookie mechanics may differ; CSRF design must be grounded in the real threat model.

## 7. When Do You Need Custom Error Pages?

An application may need user-friendly pages for:

- **401**: not validly authenticated, common in Basic/Bearer APIs; form-login apps usually redirect 302 instead of returning 401 immediately.
- **403**: authenticated but lacking permissions, invalid CSRF, or denied by the access-denied handler.
- **404**: resource or handler does not exist, *provided the request passed earlier security checks*.
- **500**: server-side processing error.

### 7.1. Do Not Fix 404/500 Rendering by Calling `permitAll` on Everything

In an app using **anyRequest().denyAll()**, a new URL without a rule can be rejected with 403 / redirected 302 before MVC knows whether a handler exists. This is a consequence of the deny-by-default policy, not necessarily a broken error page. To show 404 for a public route group, permit that route group properly and let MVC handle the missing resource.

If an error originates from an already-permitted endpoint, permitting ERROR dispatches helps render the original error. Do not use **requestMatchers("/**").permitAll()** to "restore error pages," because it opens protected endpoints too.

### 7.2. Custom Spring Boot Error Pages

In a Thymeleaf app, an error page template can be placed at **src/main/resources/templates/error/500.html**:

~~~html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Unable to process request</title>
</head>
<body>
    <h1>A server error occurred</h1>
    <p>Please try again later or contact support.</p>
</body>
</html>
~~~

This is an **optional** file, added if you want to customize UX for status 500. Similarly, you can create **templates/error/404.html** to display not-found errors. Do not print exception stack traces, user data, SQL table names, or internal configuration in views.

For a dedicated **/access-denied** page for 403, ensure the route to view that message is allowed for users who need to see it, e.g., via a specific GET rule; also configure **exceptionHandling/accessDeniedPage** if choosing this mechanism. Do not assume that merely having a Controller named `AccessDenied` causes Spring Security to route 403s there automatically.

### 7.3. Choosing the Right Error-Handling Layer

| Handler layer | Typical scope | What to remember |
| --- | --- | --- |
| AuthenticationEntryPoint | Unauthenticated user required to log in | Form-login usually redirects to /login; Bearer/Basic APIs usually return 401. |
| AccessDeniedHandler | Authenticated request denied permission | Can return 403 or forward/redirect to a denied page depending on config. |
| Spring MVC exception handling | Exceptions from controllers/services | ControllerAdvice or resolvers can handle before reaching error dispatch. |
| Spring Boot /error | Fallback error handling via ErrorController and views | Can receive ERROR dispatches; does not replace all error handlers above by default. |

If a request returns 403, look at the *cause* first: not every 403 is a missing role; it can be CSRF, a method mismatch hitting a deny rule, or the access-denied handler.

## 8. Practical Pitfalls and How to Diagnose Them

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `/login` redirects to `/login` repeatedly | `GET /login` protected by `authenticated` or `loginPage` not permitted | Permit `GET /login` properly; use `formLogin(...).permitAll()`. |
| Login page shows HTML without CSS/JS | Static URLs protected, wrong matcher, or files not in Boot's served path | Check Network tab; use `PathRequest` or narrow `permitAll` for `/css/**`, `/js/**`. |
| URL `/static/css/site.css` returns 404 | Confusing classpath path with web URL | With Boot defaults, `static/css/site.css` is served at `/css/site.css`. |
| Submitting `POST /login` returns 403 before auth | Missing CSRF token or matching session cookie | Check form `th:action`, hidden CSRF field, session/cookie. |
| `GET /login` returns 404 | Configured custom `loginPage` without an MVC handler or template | Create a `GET /login` controller and valid login template. |
| Login succeeds, but `/admin` returns 403 | Authentication lacks `ROLE_ADMIN` or wrong role mapping | Inspect actual `GrantedAuthority` values; distinguish role vs. authority. |
| `/broken` redirects to login instead of error page | ERROR dispatch blocked or error handler requires authentication | Check `DispatcherType`, filter registration, error handler; permit only needed dispatches. |
| Direct `GET /error` behaves differently from ERROR dispatch | Two requests with different `DispatcherType`s | Inspect `dispatcherTypeMatchers` and `requestMatchers` paths. |
| Private static asset downloaded publicly | Placed in public static dir or overly broad `permitAll` | Serve through an endpoint with proper authorization/ownership checks. |
| Files excluded by `WebSecurityCustomizer` ignoring | Skips desired security headers and filters | Prefer `permitAll` through the security filter chain. |
| Users get 403 on unknown URLs | `anyRequest().denyAll()` blocks before MVC | Define policies for supported URL groups; do not open the whole system. |
| Permitting all `FORWARD` dispatches to fix a bug | Internal forwards may reach sensitive handlers | Audit internal routing; apply narrow rules and test forward flows. |

Enable logging **only in development when needed**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

When investigating, check in order:

1. Exact URL and HTTP method.
2. `DispatcherType` of the request pass (`REQUEST`, `ERROR`, or `FORWARD`).
3. Selected `SecurityFilterChain`.
4. First matching `RequestMatcher`.
5. `Authentication` and authorities (do not log passwords/tokens).
6. 302/401/403/404/500 response and redirect/dispatch path.
7. Actual static files on classpath, view templates, and rendered HTML.

Do not check only for HTTP 200 HTML on `/login`; verify CSS loads, tokens are submitted, and protected requests do not slip through.

## 9. Tests You Should Have After Configuring

Minimum smoke-test matrix:

| Scenario | Expected result to confirm |
| --- | --- |
| Anonymous `GET /login` | 200, no redirect loop |
| Anonymous `GET /css/site.css` | 200, valid CSS content, processed with security headers |
| Anonymous `GET /private` | 302 to `/login` |
| Member logs in via valid form | Succeeds, redirects to `/private`, `SecurityContext` stored in session |
| Member `GET /admin` | 403 |
| Admin `GET /admin` | 200 |
| `POST /login` without valid CSRF | Rejected per CSRF policy |
| `GET /broken` | Status 500, not turned into a redirect to login |
| `GET /css/missing.css` | Missing-resource status, not redirected to login page |
| `GET` sensitive unpermitted URL | Rejected by fallback rule |
| Private file outside public static | Cannot be downloaded as a public asset |

In automated tests, you can use **spring-security-test + MockMvc**. With **MockMvc**, form login tests with CSRF can use helpers from `spring-security-test`; testing authenticated sessions or roles requires setting up the corresponding mock security context. Do not assume `@WithMockUser` tests alone catch every login flow bug: you still need at least one test exercising the real form/cookie/CSRF flow and verifying assets are served properly.

### Checking Security Headers

Resources with `permitAll` **remain inside the Spring Security filter chain**, so headers like `X-Content-Type-Options` or other security policies configured by the app have a chance to be applied. Exact headers depend on configuration/version and may be modified by a reverse proxy; do not assert an immutable fixed header list. For resources under `web.ignoring`, Spring Security's filters cannot add headers to those responses.

## 10. When Designing API-Only or Spring WebFlux Apps

**API-only applications:** may have no `login.html`, CSS, or redirect flow; instead they have authentication APIs and entry points returning 401/JSON. Even so, if there is an OpenAPI UI, API docs, JSON errors, health endpoints, or actuator, you still must design appropriate permissions. Do not expose actuator endpoints or internal docs by default just because they serve developers.

**Spring WebFlux applications:** use **SecurityWebFilterChain** and **ServerHttpSecurity.authorizeExchange(...)**. Static and login URLs still need appropriate rules, yet **Servlet `DispatcherType.ERROR/FORWARD` is not an API to copy into reactive**; WebFlux uses its own exception-handling pipeline. Directional example (fragment inside WebFlux configuration, not a standalone program):

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/css/**", "/js/**").permitAll()
        .pathMatchers("/login").permitAll()
        .pathMatchers("/private").authenticated()
        .pathMatchers("/admin").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

The fragment above expresses only authorization; a complete security chain bean still needs `formLogin`/authentication suitable for WebFlux and reactive stack error/CSRF handling.

## 11. Self-Assessment

1. If `/private` redirects to `/login` yet `/login` requires `authenticated`, what symptom do you expect?
2. Why is a file at **src/main/resources/static/css/site.css** normally accessed at **/css/site.css**, not **/static/css/site.css**?
3. How does **permitAll** for CSS differ from **web.ignoring** with respect to security headers?
4. If a user calls **GET /error** directly, is that the same as an **ERROR dispatch**?
5. Why might you need **dispatcherTypeMatchers(ERROR).permitAll()** while still keeping rules protecting **/private** and **/admin**?
6. For custom form login, which components typically handle **GET /login** and **POST /login**?
7. Why can `POST /login` need a CSRF token even when the sender is not logged in yet?
8. If `GET /broken` is permitted with `permitAll` and throws an exception, why is the expected result still 500 instead of 200?
9. What can happen when permitting all `FORWARD` dispatches without checking internal forward routes?
10. For a user's private PDF file, why should you not simply drop the file into the static folder and apply `permitAll` to `/files/**`?

**Key takeaway:** Endpoint protection must view the entire **user request journey**: loading CSS/JS/images, rendering `GET /login`, processing `POST /login`, redirecting after authentication, handling 403/404/500, and internal dispatches. Permit strictly what is needed, **prefer `permitAll` over bypassing the security filter chain for static assets**, distinguish **REQUEST** from **ERROR/FORWARD**, and keep clear protective rules for everything else.

## Official Reference Documentation

- Spring Security 6.5 — Authorize HttpServletRequests (dispatcher types, permitAll static assets): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Form Login, custom login page and CSRF form: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.3 API — PathRequest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/PathRequest.html
- Spring Boot 3.3 API — StaticResourceRequest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/StaticResourceRequest.html
- Spring Boot — Serving static content and custom error pages: https://docs.spring.io/spring-boot/reference/web/servlet.html
