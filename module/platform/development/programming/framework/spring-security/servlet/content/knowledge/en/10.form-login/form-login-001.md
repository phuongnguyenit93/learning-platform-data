# Redirect Flow from a Protected Resource to the Login Page in Spring Security Servlet

> **Scope:** Spring Security on the Servlet stack, Java 17+, Spring Framework 6 / Spring Security 6. This lesson focuses on the mechanism where **an unauthenticated user requests a protected URL → redirects to the login page → authenticates → returns to the original resource**. The example runs with Spring Boot 3.3.x to minimize server boilerplate; the filter flow, request cache, and form login remain Spring Security Servlet mechanisms.

## 1. The Problem: A User Opens a URL Requiring Authentication

Suppose an unauthenticated user without a login session directly accesses:

```text
GET http://localhost:8080/reports?period=2026-11
```

The application specifies that `/reports` can only be read by authenticated users. A commonly expected experience is:

1. The browser requests `/reports?period=2026-11`.
2. Spring Security detects that the request **does not have an authenticated user** and does not let the controller execute yet.
3. Before sending the browser to the login page, the system **saves the original request information** using the request cache.
4. The server returns a redirect response (typically HTTP **302**, with the `Location` header pointing to `/login`).
5. The browser displays the login form; the user enters a username/password and submits `POST /login` along with the CSRF token.
6. Upon successful authentication, Spring Security stores the `SecurityContext` according to the session policy, and the success handler decides the redirect destination.
7. If there is a valid saved request, the browser is redirected back to `/reports?period=2026-11`.
8. The browser sends **a new GET request** to this URL, accompanied by the session cookie. Spring Security allows access after checking authorization; the controller finally runs.

**302 does not mean logged in.** Redirecting to `/login` is an invitation to authenticate, not an authentication operation. And redirecting back to the original URL after login **does not bypass authorization**: a valid user lacking the required role can still receive **403** on the original resource.

This is the characteristic flow for **browsers using form login and HTTP sessions**. REST APIs usually need 401/403 instead of redirecting to an HTML page; the two client types should not be conflated.

## 2. Request Diagram and Participating Components

```text
Browser                          Spring Security Servlet filters
   |                                      |
   | GET /reports?period=2026-11          |
   |------------------------------------->|
   |                                      | AuthorizationFilter checks rule
   |                                      | -> unauthenticated
   |                                      v
   |                              ExceptionTranslationFilter
   |                                      |
   |                                      +-- RequestCache.saveRequest(...)
   |                                      |   (e.g., HttpSessionRequestCache)
   |                                      |
   |                                      +-- AuthenticationEntryPoint.commence(...)
   |                                      |   (LoginUrlAuthenticationEntryPoint)
   | <------------------------------------|
   | 302 Location: /login                 |
   |                                      |
   | GET /login                           |
   |------------------------------------->| DefaultLoginPageGeneratingFilter
   | <------------------------------------| or custom login controller/view
   | 200 HTML form + CSRF token           |
   |                                      |
   | POST /login (credentials + _csrf)    |
   |------------------------------------->| UsernamePasswordAuthenticationFilter
   |                                      | -> AuthenticationManager
   |                                      | -> AuthenticationProvider
   |                                      | -> SecurityContext/session
   |                                      | -> SavedRequestAwareAuthenticationSuccessHandler
   | <------------------------------------|
   | 302 Location: /reports?period=...    |
   |                                      |
   | GET /reports?period=... + cookie     |
   |------------------------------------->| SecurityContext has Authentication
   |                                      | -> re-authorize
   | <------------------------------------|
   | 200 report content                   |
```

In a servlet application, key classes have distinct roles:

| Component | Role in the redirect flow |
| --- | --- |
| `SecurityFilterChain` and `FilterChainProxy` | Decide which security filters and rules apply to the request |
| `AuthorizationFilter` | Checks `authenticated()`, `hasRole(...)`, and resource access rules |
| `ExceptionTranslationFilter` | Translates `AuthenticationException` / `AccessDeniedException` from the security layer into the appropriate HTTP handling |
| `AuthenticationEntryPoint` | Decides how to **commence authentication** when the user is unauthenticated |
| `LoginUrlAuthenticationEntryPoint` | Entry point for form login: directs to the login page |
| `RequestCache` / `HttpSessionRequestCache` | Saves the initial request so the user can return after logging in |
| `UsernamePasswordAuthenticationFilter` | Receives the form login POST, calls `AuthenticationManager`, and handles success/failure |
| `SavedRequestAwareAuthenticationSuccessHandler` | After successful login, prioritizes the saved request URL if it is still valid and allowed by configuration |
| `SecurityContext` / `SecurityContextRepository` | Stores/reads the authenticated identity according to policy, usually via the HTTP session |
| `RequestCacheAwareFilter` | Can restore the saved request on the matching follow-up visit after a redirect |

Remember to distinguish: **the entry point takes you to the login page**, **the authentication filter verifies credentials**, and **the success handler chooses the destination after login**. Not every redirect is performed by a single filter.

## 3. Why Is the Initial Request Redirected?

In a common form login configuration:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .requestMatchers("/reports").authenticated()
        .anyRequest().authenticated()
);
http.formLogin(Customizer.withDefaults());
```

This is a **Java fragment** to be placed inside an `HttpSecurity` configuration method; a complete runnable example is in section 7.

For `GET /reports` without a valid authentication:

1. `AuthorizationFilter` applies `authenticated()` and denies the request. In modern versions, the denial error may be a subtype of `AccessDeniedException`.
2. `ExceptionTranslationFilter` handles the unauthenticated situation: it can trigger authentication instead of treating it as a logged-in user with insufficient permissions.
3. When commencing authentication, the filter coordinates with `RequestCache` to save the original request, then invokes `AuthenticationEntryPoint`.
4. With form login, the entry point is `LoginUrlAuthenticationEntryPoint`, which normally sends **302** with `Location` pointing to the login page.
5. The browser follows the redirect with a **new request**. The `/reports` controller has not executed at this step.

You should not hand-write logic like "controller checks session and redirects to `/login`" when Spring Security already manages this lifecycle; it is easy to miss access rules, request cache, security context, CSRF, and the distinction between anonymous and authenticated.

### Anonymous vs. Authenticated with Insufficient Permissions

Two situations look blocked on the surface, yet follow different flows:

- **Unauthenticated** + accessing `/admin/reports`: depending on the entry point (form login), typically gets **302 to `/login`** to authenticate.
- **Authenticated** with role `USER` + accessing `/admin/reports` restricted to `ADMIN`: does not prompt for login again by default; Spring Security typically returns **403 Access Denied**.

This distinction relies on the authentication state and components such as `AuthenticationTrustResolver`. Do not infer solely from `Authentication.isAuthenticated()` because some anonymous tokens may have boolean values that do not match naive application assumptions.

## 4. RequestCache: How Is the URL Remembered Before Login?

With only `302 /login`, the application would know the user is logged in but **would not necessarily know where they wanted to go**. `RequestCache` solves this.

`HttpSessionRequestCache` (common with form login) stores a `SavedRequest` in the HTTP session. It can remember:

- The original URL along with its query string, such as `/reports?period=2026-11`.
- Request details needed for matching/restoration, depending on the implementation.
- This information does not mean storing the entire HTTP body or being allowed to replay every side effect.

Example:

```text
Turn 1 (unauthenticated)
GET /reports?period=2026-11
    -> cache saves the matching request
    -> 302 /login

Turn 2 (successful login)
POST /login
    -> success handler retrieves the saved request URL
    -> 302 /reports?period=2026-11

Turn 3 (with session)
GET /reports?period=2026-11
    -> re-checks authorization
    -> 200 if user has permission
```

The key point: **the server does not automatically "resume executing a paused controller"**. After the redirect, the browser sends a new request to the chosen URL. For browsers, it is normally necessary to ensure the **session cookie** is sent across steps so the session holding the saved request and authentication can still be found.

Do not assume every type of request can be safely "replayed": **POST/PUT/PATCH/DELETE** carry bodies and side effects. The standard form login/request cache mechanism suits navigating back to a GET page; if you want to "resubmit an interrupted form", the application must separately design idempotency/deduplication, draft storage, and CSRF handling. Do not expect Spring Security to automatically replay the body of a mutating request.

### How RequestCache and RequestCacheAwareFilter Relate

- `RequestCache.saveRequest(...)` records the original request when login is required.
- `SavedRequestAwareAuthenticationSuccessHandler` can read the saved request after successful authentication to build the redirect URL.
- `RequestCacheAwareFilter` assists in retrieving the saved request when a new request matches the criteria, according to how `RequestCache` is configured.

**Nuance in Spring Security 6:** checking for a saved request can be optimized based on a request parameter (such as `continue` in some default configurations). Therefore, do not write code assuming "`RequestCacheAwareFilter` always reads the HTTP session on every request." Use the API/configuration matching your application version and test actual requests and redirects.

### When Is a Saved Request Lost or Unused?

- The browser **does not retain the session cookie** across `/reports`, `/login`, and `POST /login`.
- You configured `NullRequestCache` or disabled request caching.
- The session does not exist, was invalidated/timed out, or a stateless configuration does not support storing the required information.
- Login was opened **directly from a menu** rather than after being blocked at a protected URL; in that case there is no corresponding saved request.
- The success handler is configured to **always redirect to a fixed URL** instead of prioritizing the saved request.
- Multiple requests occur in one session causing the saved request to be overwritten; do not treat it as an unbounded queue of every pre-login URL.
- Reverse proxy/path rewriting, context path, or redirect URL configuration is wrong, producing an unsuitable return address.
- The application has multiple `SecurityFilterChain` beans using different request caches/sessions/entry points without consistent design.

**Security note:** Redirect URLs can contain sensitive data in the query string; do not pass tokens/passwords in URLs. When using a saved request or custom success handler, avoid creating an **open redirect** from an arbitrary client-supplied `next` parameter. Enforce rules accepting only safe internal paths or an allowlist of trusted domains if cross-domain redirects are truly needed.

## 5. Where Are the Login Page and Form Handled?

With:

```java
http.formLogin(Customizer.withDefaults());
```

Spring Security configures default form login. If no custom login page is declared, the application can use **the default HTML page generated by Spring Security**.

Default URLs to remember:

| URL / method | Meaning |
| --- | --- |
| `GET /login` | Displays the default login page |
| `POST /login` | URL where the filter processes username/password |
| Form field `username` | Default username parameter |
| Form field `password` | User-entered password parameter |
| Field `_csrf` | CSRF token if CSRF protection is enabled |
| `GET /login?error` | Location form login may redirect to when authentication fails |
| `/logout` | Logout endpoint per configured policy, with appropriate method/CSRF |

In Spring Security, **`UsernamePasswordAuthenticationFilter`** processes `POST /login`; writing your own `@PostMapping("/login")` controller is unnecessary and can conflict with the filter if the mechanism is misunderstood. The filter creates a `UsernamePasswordAuthenticationToken`, calls `AuthenticationManager`, and then invokes the success/failure handler.

An incorrect password usually leads to **a redirect back to login with error info**, not automatically returning the user to the old resource as if logged in. The saved request may remain in the session for a subsequent successful login, depending on policy and how the application manages sessions.

### CSRF Is Not a Redirect Error

Because form login usually uses HTTP sessions/cookies, CSRF protection must be considered carefully. Under default configuration, POST requests require a valid CSRF token; the generated login page includes a way to submit that token.

If you craft a `POST /login` using `curl` with only username/password, **missing the CSRF token/cookie can result in 403** before authentication runs. Do not conclude that the provider checked the password as wrong, and do not disable CSRF across the entire site to "fix" this symptom.

If using a custom login page, you must render and submit the proper CSRF token field, ensure `GET /login` is publicly accessible, and keep the login processing `POST` within the right `SecurityFilterChain`.

## 6. Success Handler: Why Does Login Return to the Previous URL?

With default form login, `SavedRequestAwareAuthenticationSuccessHandler` is typically used to choose the URL after the user authenticates successfully. Simple mental model:

```text
POST /login succeeds
    |
    +-- Valid SavedRequest present and not overridden by config?
    |      +-- Yes -> redirect to original URL
    |
    +-- Missing / overridden?
           +-- redirect to default target URL or fallback
```

In the example at the start of the lesson, the post-login target URL is usually `/reports?period=2026-11`. When the browser returns to this URL, `AuthorizationFilter` **checks again** the role and authentication; a successful login does not automatically imply `permitAll`.

### `defaultSuccessUrl` Can Change Priority

Inside the security configuration method, you can write:

```java
// Fragment 1: Default URL used when there is no saved request.
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", false)
);
```

When `alwaysUse` is `false`, the saved request (if still applicable) is usually prioritized; `/dashboard` acts as the default when there is no prior request.

```java
// Fragment 2: Always redirect to dashboard, overriding saved request priority.
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", true)
);
```

The two snippets are **mutually exclusive alternatives**, not applied together. `true` means it will not necessarily return to the original URL, even when a saved request exists. If you replace `successHandler` yourself, a custom handler can also alter this behavior.

### What Happens If Login Succeeds Without Sufficient Permissions?

For example, an anonymous user visits `/admin/reports` and is sent to `/login`. They log in successfully as a user who only has `ROLE_USER`:

```text
GET /admin/reports  -> 302 /login  (unauthenticated)
POST /login         -> 302 /admin/reports (authentication succeeded)
GET /admin/reports  -> 403 (missing ROLE_ADMIN)
```

This is **correct behavior**: the saved request brings the user back to where they wanted to go, without bypassing authorization.

## 7. Runnable Example: Spring Boot 3 + Java 17 + Servlet Form Login

The example uses Spring Boot 3.3.5 (illustrative released version), Java 17+, `spring-boot-starter-web`, and `spring-boot-starter-security`.

The application has:

- `GET /public`: public access.
- `GET /reports?period=2026-11`: requires authentication, displays the user's name and query value.
- `GET /admin/reports`: requires role `ADMIN`.
- `/login` page: uses Spring Security's default generated page.
- Two test users: `lan` (`USER`) and `admin` (`ADMIN`), sharing illustrative password `demo123`.

Structure:

```text
form-login-redirect/
├── pom.xml
└── src/main/java/example/redirect/
    ├── RedirectApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 7.1. `pom.xml`

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>form-login-redirect</artifactId>
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

### 7.2. `RedirectApplication.java`

```java
package example.redirect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`: Enabling Form Login and Authorization

```java
package example.redirect;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports").authenticated()
                .anyRequest().authenticated()
        );

        // Default form login: /login, request cache, and success handler.
        http.formLogin(Customizer.withDefaults());

        // Do not disable CSRF; browser login POST requires a valid CSRF token.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(lan, admin);
    }
}
```

Explanation:

1. `/reports` only requires `authenticated()`. `/admin/**` requires authority `ROLE_ADMIN` because `hasRole("ADMIN")` uses the default `ROLE_` prefix.
2. `formLogin()` configures the login page entry point, `UsernamePasswordAuthenticationFilter`, success/failure handlers, and related components. You do not need to write a `LoginController` for this demo to run.
3. `SessionCreationPolicy.STATELESS` is not configured: form login uses HTTP sessions to share authentication across page loads and for the request cache to work.
4. `defaultSuccessUrl(..., true)` is not set, because we want to observe returning to the newly requested protected URL by priority.
5. Passwords are stored as BCrypt hashes in memory. Demo passwords are used locally; in production do not hardcode accounts and do not serve login over unencrypted HTTP.
6. `anyRequest().authenticated()` is the fallback rule, preventing new URLs from being accidentally exposed. Static assets, custom login pages, and public APIs must be explicitly designed when expanding the application.

### 7.4. `DemoController.java`: Endpoints to Observe Redirect Behavior

```java
package example.redirect;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String root() {
        return "home:public";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/reports")
    public String reports(
            @RequestParam(defaultValue = "current") String period,
            Authentication authentication) {
        return "reports:" + authentication.getName() + ":" + period;
    }

    @GetMapping("/admin/reports")
    public String adminReports(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

The two controller methods `reports` and `adminReports` only execute after the filter chain has allowed the request. `@RestController` returns plain text strings for easy observation without needing a template engine; **the login page is still the HTML page generated by Spring Security**.

## 8. Running and Testing Redirects in a Browser

### 8.1. Starting the Application

In the directory containing `pom.xml`, using Maven 3.9+ and JDK 17+:

```bash
mvn spring-boot:run
```

With default configuration, embedded Tomcat serves on `http://localhost:8080`.

### 8.2. Testing the Happy Path Preserving the Query String

1. Open an unauthenticated browser window (you can use a new private window) and visit `http://localhost:8080/reports?period=2026-11`.
2. Observe the browser address change to `http://localhost:8080/login`. This is the redirect to the entry point; **the reports controller has not run yet**.
3. Log in with username `lan`, password `demo123` on the generated form.
4. After a successful login, the browser returns to `/reports?period=2026-11`. The page displays exactly:

```text
reports:lan:2026-11
```

Thus, the saved request preserved **the path and query string**, and authentication was read back on the new request. During this process, the browser receives/sends a session cookie; when Spring Security applies session fixation protection, the session ID may change upon login, so do not rely on a fixed `JSESSIONID` value.

### 8.3. Testing Public Paths and Admin Rules

- When unauthenticated, `GET /public` returns `public:ok`; no redirect.
- When unauthenticated, `GET /admin/reports` typically redirects to `/login`.
- After logging in as `lan` and visiting `/admin/reports`: the server denies with HTTP **403** because `lan` has `ROLE_USER`, not `ROLE_ADMIN`. Do not automatically treat this as a failed login.
- Log out of `lan`'s session using the standard flow and log in as `admin` with the same demo password; `GET /admin/reports` returns:

```text
admin:admin
```

To properly observe the saved request, start a new session from **the protected URL**, rather than opening `/login` directly first and expecting a pre-existing original URL.

### 8.4. Inspecting HTTP 302 with curl Without Simulating Form Login

```bash
# Use a real GET to trigger the request-saving flow and 302.
curl -i -c cookies.txt \
  'http://localhost:8080/reports?period=2026-11'

# Fetch the login page, sending the saved session cookie.
curl -i -b cookies.txt 'http://localhost:8080/login'
```

In the first request, the relevant headers look like:

```text
HTTP/1.1 302
Location: http://localhost:8080/login
Set-Cookie: JSESSIONID=...; ...
```

This is a **header-format illustration**, not a fixed byte-for-byte transcript: the `Location` address may be absolute or relative depending on infrastructure, and `Set-Cookie` depends on cookie/session configuration. `curl` does not follow redirects by default; use `-L` if you want to follow redirects, while understanding the order of new requests.

**Do not use `curl -I` (HEAD) expecting to accurately simulate a browser GET visit.** And do not POST to `/login` with `curl` using only username/password: form login has CSRF enabled, requiring extracting the dynamic token from the page, keeping the session cookie, and submitting the token back. A browser is more convenient for testing this end-to-end flow.

### 8.5. Response Codes to Distinguish

| Response | When in the example? | Who decides? |
| --- | --- | --- |
| **302 → `/login`** | Anonymous user requests a protected resource | `ExceptionTranslationFilter` + `LoginUrlAuthenticationEntryPoint` |
| **200 HTML login** | `GET /login` | Default generated login page or custom login view |
| **302 → saved URL** | `POST /login` with valid credentials and CSRF | Authentication filter + success handler |
| **302 → `/login?error`** | Form login fails due to invalid credentials per default policy | Failure handler |
| **200 resource** | Browser returns to the saved URL, authenticated and authorized | Authorization + controller |
| **403** | Logged in but missing role; or POST request missing CSRF token | Access-denied / CSRF mechanisms |
| **401** | Can be seen with HTTP Basic/Bearer entry points, not the default browser form login flow | Corresponding entry point |

HTTP status also depends on request type, custom filters/handlers, and application infrastructure. Do not assume "every unauthenticated request returns 302" if the application has multiple authentication mechanisms.

## 9. Customizing the Login Page: Avoiding Redirect Loops

When replacing the generated page with your own page, configuration can look like this:

```java
// Fragment in SecurityFilterChain, replacing default formLogin.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public", "/signin", "/error").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/perform_login")
        .permitAll()
);
```

This is a **replacement configuration fragment**, not to be merged on top of the configuration in section 7. When using it:

- You must create **`GET /signin`** yourself (controller + HTML template or view) to display the form. Spring Security does not automatically generate a custom `/signin` page.
- The form needs `method="post"`, `action="/perform_login"` accounting for the context path, username/password fields matching the default or customized names, and **a valid CSRF token**.
- The login page URL, login processing URL, and essential static assets must be accessible anonymously; if `/signin` itself requires authentication, the server may redirect to itself repeatedly.
- `loginProcessingUrl` is **an endpoint handled by the security filter**, so a POST controller at the same URL is not needed.
- When using multiple `SecurityFilterChain` beans, ensure the login URL and login processing URL belong to **the chain configured with formLogin**. If the login URL matches another chain, the browser may get 404, 401, or a redirect loop.

A custom login page typically uses Thymeleaf/JSP or an SPA frontend. If the frontend is on a different origin, clearly design CORS, cookies, CSRF, and callback URLs rather than randomly changing security filter order just to "make it work."

### Customizing the Post-Login Target

```java
// Fragment: /dashboard is used only when there is no saved request.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", false));
```

```java
// Alternative fragment: always go to /dashboard, overriding saved request priority.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", true));
```

The two snippets are **two alternative options**, not simultaneous configurations. If UX policy requires always landing on a fixed page after login, choose the second form; if the goal is returning users to where they were navigating, keep the handler prioritizing the saved request.

### Customizing Request Cache

```java
// Fragment when you INTENTIONALLY do not want to save the initial request.
http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
```

Requires importing `org.springframework.security.web.savedrequest.NullRequestCache`. With this approach, do not expect the application to return to the original protected URL via the default saved request mechanism. For stateless REST APIs, you typically choose an entry point returning 401/403 rather than saving requests to redirect to form login.

## 10. REST APIs and Multiple SecurityFilterChains

Applications with both a web UI and APIs should consider separating chains:

- WEB: form login, sessions, request cache, and redirects to HTML pages.
- API: Bearer token or Basic by design; usually needs **HTTP 401** when unauthenticated and **403** when lacking permission; browsers should not be sent to `/login`.

Separate **illustrative fragment**, do not paste directly into the section 7 application as-is:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
```

This snippet requires `@Configuration`, `@EnableWebSecurity`, and appropriate imports for `Order`, `SecurityFilterChain`, `HttpSecurity`, `SessionCreationPolicy`, and `NullRequestCache`; it only illustrates **policy separation**, not a standalone runnable app. Place the API chain **before** the WEB fallback so `/api/**` is not caught by the web chain and redirected to form login.

Do not assume "stateless means CSRF can always be safely disabled"; if an API uses credentials automatically sent by browsers such as cookies or certain Basic auth cases, evaluate CSRF under the client/threat model. If the API only accepts Bearer tokens explicitly sent in headers, a separate CSRF policy for the API chain can be chosen after verifying those conditions.

## 11. Common Errors and How to Find the Root Cause

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| `GET /reports` returns 200 when not logged in | Overly broad `permitAll` rule or request bypasses the security chain | Check matchers, filter registration, and authorization configuration |
| Multiple redirects between `/login` and `/login` | Login page is guarded by an auth rule, or wrong login page URL | Allow anonymous access to the login page and required resources |
| After login always goes to `/` instead of reports | No saved request, lost session cookie, custom handler, or `defaultSuccessUrl(..., true)` | Check RequestCache, session, handler, and access flow |
| After login returns to reports but gets 403 | User lacks the required authority | This is authorization, not a request cache bug |
| `POST /login` returns 403 | Missing/invalid CSRF token or session cookie | Check form action, CSRF hidden field, and cookie |
| `POST /login` returns 404 | Wrong `loginProcessingUrl`, request enters wrong chain, or no processing filter | Verify login processing URL and matcher |
| `GET /login` returns 404 with custom login page | Only set `loginPage` without creating a controller/view | Create the endpoint rendering the login page |
| API gets redirected to HTML instead of 401 | Web chain handles API or unsuitable entry point | Separate API chain/entry point, check `@Order` |
| Saved request returns to wrong host/scheme | Incorrect reverse proxy headers, context path, or redirect config | Check trusted forwarded headers and URL generation |
| Login succeeds but browser stays anonymous | Cookie not sent, stateless policy, context not saved, or broken session | Check `SecurityContextRepository`, cookies, and session |
| Browser still shows cached page after logout | Browser/proxy caching or logout not invalidating properly | Inspect cache headers, logout handler, and session invalidation |

### How to Debug Request by Request

1. Record the **initial URL** the user opened, method, query string, and HTTP status.
2. Check which security chain was selected, which `authenticated()`/`hasRole()` rule applied, and the anonymous state.
3. Check the first redirect: does `Location` point to the right login URL? Is there a session cookie when saving the request is needed?
4. Check GET login page: does the response have a form with the right action, CSRF token, and required CSS/JS?
5. Check POST login: did the filter process it? Did authentication succeed or fail? Was session fixation protection / session ID migration handled properly?
6. Check `SavedRequestAwareAuthenticationSuccessHandler`: is there a saved request, or was it overridden by `defaultSuccessUrl(..., true)` or a custom handler?
7. Check GET back to the original URL: does the browser send the new session cookie? Does the user have the required authority? If 403, that is post-login access control.

You can enable logging in development to observe filters and authentication processing:

```properties
logging.level.org.springframework.security=DEBUG
```

Do not log passwords, CSRF tokens, raw session cookies, or full `Authorization` headers. When investigating in production, mask personal data and secrets per log governance policy.

## 12. Cases to Self-Verify

| Test case | Expected result |
| --- | --- |
| Anonymous visits `/public` | 200, no redirect |
| Anonymous visits `/reports?period=2026-11` | 302 to login |
| Log in as `lan` after visiting reports | 302 to saved URL, then 200 with body `reports:lan:2026-11` |
| Open `/login` directly and log in without prior protected URL access | Redirects to default/fallback target URL, no saved reports URL |
| Log in with wrong password | No authenticated session issued; failure handler returns to login page with error |
| Anonymous visits `/admin/reports` | 302 to login |
| After logging in as `lan`, visit admin | 403 because `ROLE_ADMIN` is missing |
| After logging in as `admin`, visit admin | 200 with body `admin:admin` |
| Manually POST login without valid CSRF token | Typically rejected with 403 |
| Enable `defaultSuccessUrl("/dashboard", true)` | Succeeds to dashboard instead of prioritizing saved request |
| Disable request cache via `NullRequestCache` | No longer returns to original URL via default saved request behavior |

In integration tests, verify **two separate requests**: the first request returns a redirect to login; after login, the browser or test client retains the session/cookies and requests the original URL again. Do not test only `/login` and assume the original request-saving mechanism definitely works.

## 13. Practical Implementation Checklist

- [ ] Define protected resources with `authorizeHttpRequests`, rather than relying on controllers to redirect manually.
- [ ] Use the right entry point for the client type: form login for browsers, 401/403 for APIs.
- [ ] Ensure the login page/login processing URL and essential static resources are not blocked by security rules into a redirect loop.
- [ ] Verify `RequestCache` and session cookies when returning to visited URLs is needed; do not store secrets in query strings.
- [ ] Keep CSRF protection for form login and state-changing operations using cookies/sessions.
- [ ] Understand that saved requests do not replay request bodies or side effects of POST/PUT.
- [ ] Review the success handler: prioritize saved request or always redirect to a fixed target; configure intentionally.
- [ ] Always re-check authorization after login, especially for URLs requiring higher roles.
- [ ] Protect session cookies with HTTPS, appropriate `Secure`, `HttpOnly`, `SameSite`, and session fixation protection.
- [ ] With reverse proxies or multiple security chains, test redirect host/scheme/context path and actual permissions.
- [ ] Add happy-path and failure-path tests covering session timeout, blocked cookies, and wrong login attempts.

**Key takeaway:** When an anonymous user opens a protected resource, Spring Security Servlet can **intercept the request → save `SavedRequest` → use `AuthenticationEntryPoint` to redirect to `/login` → authenticate via form → success handler redirects back to `SavedRequest` → re-check permissions on the new request**. The redirect itself does not replace authentication or authorization; it only bridges the user experience between the original resource and the login page.