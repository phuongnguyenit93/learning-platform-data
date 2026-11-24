# requiresAuthenticationRequestMatcher: Selecting the Right Requests to Authenticate

## Objectives and Core Answer

In Spring Security Servlet, an authentication filter should not attempt login on every request. For example, form login only needs to intercept an **HTTP POST to the login processing endpoint**, not every GET of the login page, CSS download, API call, or logout request. `AbstractAuthenticationProcessingFilter` solves this with a `RequestMatcher` configured through **`setRequiresAuthenticationRequestMatcher(...)`**.

When a request passes through the filter:

- If `requestMatcher.matches(request) == false`, the filter **does not call `attemptAuthentication(...)`** and forwards the request to the rest of the filter chain.
- If it returns `true`, the filter starts the authentication flow: it invokes `attemptAuthentication(...)` to build/verify an `Authentication`, then handles success, failure, or an incomplete authentication step.
- The matcher **does not check passwords**, **does not enforce access control**, **does not select the `SecurityFilterChain`**, and **does not replace CSRF protection**.
- Choosing the right matcher means scoping the filter to **the exact HTTP method, URL, and technical conditions** that the authentication mechanism actively supports; never turn "has a login-like path" into "trusted".

This lesson belongs to the **Filter Integration** group of the *Spring Security - authentication* module, focusing on Servlet `AbstractAuthenticationProcessingFilter` and `UsernamePasswordAuthenticationFilter` in Spring Security 6.x. The examples use **Java 17+, Spring Boot 3.x**, and `PathPatternRequestMatcher` (available in Spring Security 6.5). WebFlux uses a different `ServerWebExchangeMatcher` API, so the Servlet snippets do not apply verbatim.

After this lesson, you should be able to:

1. Distinguish between a filter **being invoked** and a filter **deciding whether to attempt authentication**.
2. Pinpoint where `requiresAuthentication(...)` and `requiresAuthenticationRequestMatcher` live in `AbstractAuthenticationProcessingFilter`.
3. Match `POST /auth/login` exactly while excluding `GET /auth/login`, `POST /auth/login/extra`, and other API paths.
4. Distinguish the authentication processing matcher from `http.securityMatcher(...)` and `authorizeHttpRequests(...requestMatchers(...))`.
5. Configure standard form login via `loginProcessingUrl(...)`, and know when calling the setter directly on a custom filter is actually needed.
6. Test both **matching requests** and **non-matching requests**, including with a context path.
7. Recognize pitfalls around HTTP methods, CSRF, multiple filter chains, servlet paths, and doubly registered filters.

## 1. Filtering Layers: Three Distinct Decisions

An HTTP request arriving at Spring Security typically passes through multiple selection layers:

~~~text
HTTP request
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +-- (A) Which SecurityFilterChain matches?
    |       http.securityMatcher(...)
    |
    v
Filters in the selected chain
    |
    +-- (B) Should this authentication filter process it?
    |       requiresAuthenticationRequestMatcher.matches(request)
    |            false -> chain.doFilter(...)
    |            true  -> attemptAuthentication(...)
    |
    v
Request Authentication/Authorization
    |
    +-- (C) Is the request allowed to access the resource?
            authorizeHttpRequests(...requestMatchers(...))
~~~

Although all three layers can use `RequestMatcher`, their purposes differ:

| Layer | Configuration / API | Question answered | When it does not match |
| --- | --- | --- | --- |
| Select **`SecurityFilterChain`** | `http.securityMatcher(...)` | Does this chain apply to the request? | `FilterChainProxy` evaluates the next chain |
| Select **authentication attempt** within a filter | `setRequiresAuthenticationRequestMatcher(RequestMatcher)` | Should this filter attempt to authenticate the request? | Filter skips the attempt and delegates forward |
| Select **authorization rule** | `authorizeHttpRequests(a -> a.requestMatchers(...))` | When accessing a resource, which rule grants/denies access? | Evaluates the next rule in the selected chain |

For example, `POST /auth/login` may be intercepted by the form-login filter, whereas `GET /auth/login` passes through that filter **without triggering a login attempt**. Afterwards, the GET may still be intercepted by `AuthorizationFilter` requiring authentication, redirected to the login page, return 404, or be handled by a controller depending on actual rules and endpoints. **Not matching the authentication matcher does not mean the request is automatically permitted.**

### 1.1. Being Invoked vs. Attempting Authentication

`AbstractAuthenticationProcessingFilter#doFilter(...)` executes whenever a request enters a filter chain containing that filter instance. Inside, it calls `requiresAuthentication(request,response)`, which evaluates the `RequestMatcher` configured via `setRequiresAuthenticationRequestMatcher(...)`.

Responsibility outline:

~~~text
AbstractAuthenticationProcessingFilter.doFilter(...)
    |
    +-- requiresAuthentication(request, response)?
    |        |
    |        +-- false -> filterChain.doFilter(request,response)
    |        |
    |        +-- true  -> attemptAuthentication(request,response)
    |                     |
    |                     +-- Authentication result (success)
    |                     |      -> session strategy + success flow
    |                     |
    |                     +-- AuthenticationException
    |                     |      -> failure flow
    |                     |
    |                     +-- null (mechanism still continuing)
    |                            -> return, await next step
~~~

This is a **logic diagram**, not verbatim Spring Security source code. Some filters have their own conversion/continuation mechanisms, yet `AbstractAuthenticationProcessingFilter`'s contract clearly states the filter starts authentication only when the matcher matches. Success/failure handling must rely on configured `AuthenticationManager`, `SecurityContextRepository`, handlers, and session strategies.

### 1.2. Why Must It Match the Exact Request?

A matcher that is too **broad** can cause:

- The filter trying to read username/password on non-login endpoints.
- A `GET /login` (for rendering the form) being mistakenly treated as a login attempt.
- `POST /api/orders` or `POST /logout` being hijacked by the login filter.
- Request data being parsed and logged out of context, expanding attack surface and business bugs.
- Two authentication filters competing for the same URL; the earlier one may "swallow" the request.

A matcher that is too **narrow** can cause:

- Valid form submissions never triggering `attemptAuthentication`.
- Clients receiving `404`, `405`, redirects, or `403` from another layer, which developers misread as a wrong password.
- Context paths or servlet paths causing the actual path not to match.
- Wrong HTTP method restrictions (form POST registered while matcher only accepts GET).

Choosing the right matcher both **separates responsibilities** and makes behavior testable, though it must still pair with a real authentication policy.

## 2. API of AbstractAuthenticationProcessingFilter

`org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter` is the base class for many HTTP login-processing filters, notably `UsernamePasswordAuthenticationFilter`.

Key methods:

~~~java
// Illustrative signatures, abbreviated for Spring Security 6.x.
// This is not a class to recreate yourself.

public final void setRequiresAuthenticationRequestMatcher(
    RequestMatcher requestMatcher
);

protected boolean requiresAuthentication(
    HttpServletRequest request,
    HttpServletResponse response
);

public abstract Authentication attemptAuthentication(
    HttpServletRequest request,
    HttpServletResponse response
) throws AuthenticationException, IOException, ServletException;

public void setFilterProcessesUrl(String filterProcessesUrl);
~~~

`RequestMatcher` is an interface with `boolean matches(HttpServletRequest request)`. It determines **whether to attempt authentication on the current request**, and is not responsible for creating tokens or verifying secrets.

### 2.1. What Does the Setter Affect?

When you call:

~~~java
filter.setRequiresAuthenticationRequestMatcher(loginMatcher);
~~~

the filter uses `loginMatcher` for `requiresAuthentication` decisions on requests reaching **that filter instance**. It **does not** register the filter into `SecurityFilterChain`, affect other filter instances, or sync with authorization rules unless you configure them.

If a custom filter extends `AbstractAuthenticationProcessingFilter`, you can pass the matcher directly in the constructor:

~~~java
public CustomLoginFilter(
    RequestMatcher loginMatcher,
    AuthenticationManager manager
) {
    super(loginMatcher, manager);
}
~~~

This is a **constructor fragment** of a custom class; the custom filter still must implement `attemptAuthentication(...)` and be wired properly. Passing the matcher at construction avoids forgetting the setter. Different versions/implementations have other constructor overloads; check the Javadoc for your exact version.

### 2.2. setFilterProcessesUrl vs. setRequiresAuthenticationRequestMatcher

`setFilterProcessesUrl("/auth/login")` is a convenience setter for the filter's processing URL. `setRequiresAuthenticationRequestMatcher(...)` lets you supply a custom `RequestMatcher`, including HTTP method, pattern, and combined conditions.

**Do not call both setters assuming their conditions are "ANDed"**: the setters can replace the current matcher, so whichever runs last may overwrite your earlier condition. Pick one clear configuration source and test the exact filter instance with real URLs and methods.

### 2.3. Default UsernamePasswordAuthenticationFilter

`UsernamePasswordAuthenticationFilter` processes form logins with `username` and `password` parameters. Under standard form login configuration, the default processing endpoint is **`POST /login`**; `GET /login` typically displays the login page.

When using `http.formLogin(...)`, change the processing URL via the DSL:

~~~java
http.formLogin(form -> form
    .loginProcessingUrl("/auth/login")
    .permitAll()
);
~~~

This is a **fragment inside `HttpSecurity` configuration**, not a standalone Java file. For login to actually work, the client must submit the form with the right **HTTP method**, **URL**, **parameter names**, and **CSRF token** when CSRF is enabled. Do not manually create an extra `UsernamePasswordAuthenticationFilter` when the DSL already creates one.

## 3. Matching Path and HTTP Method Together

A form-style login request can be identified by:

~~~text
method = POST
path   = /auth/login
~~~

Matching only the path **without checking the method** lets GET, PUT, or DELETE on that URL trigger an authentication attempt. Checking only the method without the path is even worse: every POST in the application could be intercepted.

Starting in Spring Security 6.5, you can use `PathPatternRequestMatcher`:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher
    .PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher loginMatcher =
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login");
~~~

**Import note:** The snippet above wraps the package name across two lines for readability, but **Java does not allow line breaks mid-package when importing a class**. In a runnable file, write the import on one line:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
~~~

`PathPatternRequestMatcher.Builder.matcher(HttpMethod, String)` checks both method and path. Paths are written **relative to the context path**. For an app at root, `/auth/login` is the path; if deployed under `/shop`, the client URL is `/shop/auth/login` while the matcher is still typically written `/auth/login`. For servlets with a non-default prefix, consider `basePath(...)` per mapping.

To avoid confusion, the Java file in the runnable example below puts imports on standard single lines. Trailing slashes or pattern wildcards can affect results; use **exact paths** and avoid `/**` for login unless genuinely required.

### 3.1. Table of Matched and Ignored Requests

With matcher `POST /auth/login`:

| Request | Matches? | Why |
| --- | --- | --- |
| `POST /auth/login` | `true` | Correct method and exact path |
| `GET /auth/login` | `false` | Wrong method |
| `PUT /auth/login` | `false` | Wrong method |
| `OPTIONS /auth/login` | `false` | CORS preflight is not login |
| `POST /auth/login/extra` | `false` | Extra path segment |
| `POST /auth/login2` | `false` | Different exact path |
| `POST /api/orders` | `false` | Different business request |
| `POST /auth/login?next=/me` | `true` | Query string does not alter matched path |
| App has context path `/shop`, client sends `POST /shop/auth/login` | `true` when matcher relative to context path is configured properly | `/shop` is context path, not login path |

Values assume the default path parser and compatible servlet mappings; if the app uses reverse proxy rewrites, multiple servlets, or custom path parsers, test in the real deployment setup.

### 3.2. Do Not Treat Headers as Proof of Login

Some authentication filters only process requests with specific headers, such as `X-Requested-With` or `Content-Type: application/json`. A header can help **select a parser**, yet it **does not prove** the client is trustworthy. Attackers can supply arbitrary headers.

If a filter consumes JSON credentials, the matcher should restrict **method and URL**, while the parser checks content type, body size, and valid formatting; the authentication provider still verifies credentials. Never treat `X-Internal: true` or any self-declared header as permission to bypass passwords.

### 3.3. Path, Context Path, and Servlet Path

Suppose the deployment is:

~~~text
https://example.com/shop/api/auth/login
                     ^^^^^
                     context path = /shop
                           ^^^^
                           servlet/base path = /api
                                ^^^^^^^^^^^
                                endpoint under servlet = /auth/login
~~~

With `PathPatternRequestMatcher.withDefaults()`, patterns are relative to the **context path**, and if you want paths scoped under a servlet prefix, the builder offers `basePath("/api")`. In an example where `DispatcherServlet` is mapped under `/api/*`:

~~~java
RequestMatcher loginMatcher =
    PathPatternRequestMatcher.withDefaults()
        .basePath("/api")
        .matcher(HttpMethod.POST, "/auth/login");
~~~

This fragment matches `/api/auth/login` inside the application after stripping the context path. If custom servlet mappings, forwarded headers, or proxy rewrites differ, inspect the actual request path Spring Security sees. **Do not** copy the external browser URL verbatim into the matcher if it duplicates the context path.

### 3.4. Matchers and Query Parameters

The URL `/auth/login?continue=/home` still has path `/auth/login`. Path/method matchers do not validate the `continue` parameter. If the login success handler redirects using a parameter, validate redirect targets to prevent open redirects. Never put usernames/passwords in query strings; they can end up in browser history, logs, or referrers.

## 4. A Right Matcher Alone Is Not Enough to Log In

An authentication filter also needs:

1. Proper placement **inside `SecurityFilterChain`**, without misordering.
2. An `AuthenticationManager` to perform verification.
3. Credential parsing matching the request's content type.
4. Appropriate success/failure handlers and `SecurityContext` policy.
5. A session strategy if using session-based login.
6. CSRF protection, TLS, rate limiting, and auditing aligned with your threat model.

For example, the matcher accepts `POST /auth/login`, yet the client sends a JSON body while standard `UsernamePasswordAuthenticationFilter` reads **form parameters** `username` and `password`. JSON will not be parsed automatically. For JSON login, use an explicitly designed converter/filter; do not tweak the matcher thinking that fixes body parsing.

### 4.1. A Matcher Does Not Replace PasswordEncoder

A matching request only says "this is a candidate login attempt". The provider still has to do:

~~~text
username/password from filter
        |
        v
unauthenticated UsernamePasswordAuthenticationToken
        |
        v
AuthenticationManager -> DaoAuthenticationProvider
        |
        +--> UserDetailsService reads stored hash/status
        +--> PasswordEncoder.matches(rawPassword, storedHash)
        +--> checks account flags and policies
        |
        v
Successful Authentication or AuthenticationException
~~~

Even with a matching request, a user can still receive an authentication failure due to a wrong password, disabled/locked/expired account, or unsupported token type. The matcher **never sets `Authentication.isAuthenticated()==true`**.

### 4.2. A Matcher Does Not Replace Authorization

An endpoint with rules:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

These rules govern **resource access permissions**. They do not change when `UsernamePasswordAuthenticationFilter` calls `attemptAuthentication`. Conversely, the authentication filter's setter does not make `/admin` public.

## 5. Three Matchers Often Confused in HttpSecurity

### 5.1. http.securityMatcher — Selects the SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **fragment** of a configuration class; import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. `FilterChainProxy` routes only `/api/**` requests into this chain; other requests try the next chain. If **no chain matches**, a request can go **unprotected by Spring Security**. Always include a catch-all security chain with appropriate default protections.

### 5.2. authorizeHttpRequests.requestMatchers — Selects Authorization Rules

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

These matchers apply **within the selected chain** and do not decide whether the form-login filter runs. `permitAll()` does not mean "bypass all filters": authentication filters can still inspect matching requests in that chain.

### 5.3. requiresAuthenticationRequestMatcher — Selects Attempts Inside a Filter

~~~java
UsernamePasswordAuthenticationFilter loginFilter =
    new UsernamePasswordAuthenticationFilter();

loginFilter.setRequiresAuthenticationRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login")
);
~~~

This is a **fragment for custom wiring**, not a complete configuration. You must still wire the authentication manager, session strategy, context repository/handlers, and register the filter exactly once in the security chain. For **standard form login**, `formLogin(f -> f.loginProcessingUrl("/auth/login"))` is much simpler.

### 5.4. Bug Example When Two Chains Do Not Intersect

A configuration containing only:

~~~java
http
    .securityMatcher("/api/**")
    .formLogin(form ->
        form.loginProcessingUrl("/auth/login")
    );
~~~

This chain **is not selected** for `POST /auth/login`, so the login filter **never gets a chance** to process the request. The bug may manifest as 404, a redirect, or fallback chain behavior. Do not try to fix it by changing `PasswordEncoder`, because credentials never even reach a provider.

There are two fixes depending on design:

- Move the login endpoint inside the chain's prefix, e.g., `/api/auth/login`, ensuring the form action and matcher align.
- Or let the chain holding the login filter also match `/auth/login` via a combined `securityMatcher(RequestMatcher)`, plus a catch-all chain protecting everything else.

When using multiple chains, specify `@Order` explicitly. Higher-priority chains are picked first; a single request **does not run sequentially through all `SecurityFilterChain`s**. That differs from a composite `OrRequestMatcher` checking multiple conditions inside a single filter.

## 6. Runnable Spring Boot 3.x / Java 17+ Example

This example uses **built-in form login** and configures the processing URL to `/auth/login`. The goal is to show selecting login requests by exact method/path without unnecessarily reimplementing an authentication filter from scratch.

### 6.1. Creating the Project

Create a project with Spring Initializr:

- Java 17 or 21, Spring Boot **3.x**, Maven.
- Group `com.example`, artifact `login-request-matcher`.
- Package `com.example.demo`.
- Dependencies: **Spring Web** and **Spring Security**.

The project needs `spring-boot-starter-web` and `spring-boot-starter-security` generated by Initializr. No database is needed: an in-memory test user is used. Main file tree:

~~~text
src/main/java/com/example/demo/LoginMatcherApplication.java
src/test/java/com/example/demo/LoginMatcherGateTest.java
pom.xml
~~~

### 6.2. Complete Spring Boot Source

Create **`src/main/java/com/example/demo/LoginMatcherApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginMatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginMatcherApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/auth/login")
                .permitAll()
            )
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication auth) {
            return "Hello " + auth.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Explanation:

- `formLogin(...loginProcessingUrl("/auth/login"))` configures the **credential-processing endpoint**. It differs from the **form display page**, which defaults to `GET /login` generated by Spring Security when no custom `loginPage` is declared.
- The standard login filter should only attempt authentication on form POSTs to the configured processing URL, not treat every request as a login.
- `PasswordEncoder` hashes the demo password; the provider verifies real passwords.
- `/public` can be accessed anonymously; `/me` requires authentication; `/admin` requires `ROLE_ADMIN`, whereas Alice only has `ROLE_USER`.
- No `@PostMapping("/auth/login")` controller is needed in MVC: the login processing endpoint is provided by the **filter** when the chain matches. Writing a duplicate controller at that path causes confusion over what handles the request.
- The example retains default CSRF; never disable CSRF just to test POST login with curl.

**Never use hardcoded demo passwords, plain HTTP without TLS, or in-memory users in production.** The purpose here is illustrating filter routing.

### 6.3. Running and Testing in a Browser

In the project directory:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

How to test:

1. Open `http://localhost:8080/public` → body `public`.
2. Open `http://localhost:8080/me` while logged out → normally redirects to `/login`.
3. The default login page generates an HTML form whose action targets `/auth/login`; sign in as **alice / demo-pass**.
4. Visit `/me` again → body **`Hello alice`**.
5. Visit `/admin` as Alice → **HTTP 403**, lacking `ROLE_ADMIN`.
6. Log out via the built-in endpoint, then visit `/me` → requires logging in again.

If you configure a custom login page, the form must submit **POST `/auth/login`**, use matching `username`/`password` parameter names, include a valid CSRF token, and carry the browser/session cookie. If the form mistakenly POSTs to `/login` after changing the processing URL, the login filter will ignore it.

### 6.4. Do Not Mechanically Infer Response Status from the Matcher

| Request | Login filter attempts? | Response also depends on |
| --- | --- | --- |
| `GET /login` | No | Generated login page or custom page |
| `POST /auth/login`, valid CSRF/credentials | Yes | Success handler usually redirects |
| `POST /auth/login`, wrong password, valid CSRF | Yes | Failure handler usually redirects `/login?error` |
| `POST /auth/login`, missing CSRF | May be blocked **before reaching filter** | `CsrfFilter` may return 403 |
| `GET /auth/login` | No | Authorization, redirect, or 404; not guaranteed 405 |
| `POST /api/orders` | No | Controller and other filters/rules |
| `OPTIONS /auth/login` | Not a POST login | CORS/preflight rules |

Because the CSRF filter usually runs before the authentication filter, a `POST /auth/login` missing CSRF can be rejected without `attemptAuthentication` ever being called. **A matcher can match path/method yet the request still never reaches the attempt step.** To test the filter directly, use the unit test below; to test HTTP end-to-end, include a valid CSRF token/cookie.

## 7. Unit Testing Request Selection Directly

The app runs in a browser, yet to **verify the matcher and filter gate precisely**, use a minimal `AbstractAuthenticationProcessingFilter` in JUnit. The test filter counts `attemptAuthentication` invocations and returns `null`, avoiding fake logins or password checks. Per the filter's contract, returning `null` signals authentication is incomplete so the filter returns without continuing the chain on that attempt.

### 7.1. Test Dependency

Add `spring-boot-starter-test` to `pom.xml` if the project does not already have it:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Test provides `MockHttpServletRequest`/`MockHttpServletResponse`. `spring-security-test` is not required for the unit test below because it does not use MockMvc security integration helpers.

### 7.2. Complete JUnit 5 File

Create **`src/test/java/com/example/demo/LoginMatcherGateTest.java`**:

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LoginMatcherGateTest {

    static final class CountingLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        int attempts = 0;

        CountingLoginFilter(RequestMatcher matcher) {
            super(matcher, authentication -> authentication);
        }

        @Override
        public Authentication attemptAuthentication(
            HttpServletRequest request,
            HttpServletResponse response
        ) {
            attempts++;
            // Null: in this fixture we only measure whether it was invoked.
            // Never return null like this for real login handling.
            return null;
        }
    }

    private void assertSelection(
        String method,
        String uri,
        String contextPath,
        String servletPath,
        boolean expectedAttempt
    ) throws Exception {

        RequestMatcher matcher =
            PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.POST, "/auth/login");

        CountingLoginFilter filter = new CountingLoginFilter(matcher);

        MockHttpServletRequest request =
            new MockHttpServletRequest(method, uri);
        request.setContextPath(contextPath);
        request.setServletPath(servletPath);

        MockHttpServletResponse response =
            new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean(false);

        FilterChain chain = (req, res) -> continued.set(true);
        filter.doFilter(request, response, chain);

        assertEquals(
            expectedAttempt ? 1 : 0,
            filter.attempts
        );
        assertEquals(
            !expectedAttempt,
            continued.get()
        );
    }

    @Test
    void postExactPathAttemptsAuthentication() throws Exception {
        assertSelection(
            "POST", "/auth/login", "", "/auth/login", true
        );
    }

    @Test
    void wrongMethodsAndPathsDoNotAttempt() throws Exception {
        assertSelection(
            "GET", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "PUT", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "OPTIONS", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "POST", "/auth/login/extra",
            "", "/auth/login/extra", false
        );
        assertSelection(
            "POST", "/auth/login2", "", "/auth/login2", false
        );
        assertSelection(
            "POST", "/api/orders", "", "/api/orders", false
        );
    }

    @Test
    void contextPathIsNotPartOfMatcherPattern() throws Exception {
        assertSelection(
            "POST", "/shop/auth/login",
            "/shop", "/auth/login", true
        );
    }
}
~~~

**What is being tested?**

- Request matching method/path → `attemptAuthentication` is called exactly **once**, and the filter does not call `chain.doFilter` because the fixture intentionally returns `null`.
- Non-matching request → `attemptAuthentication` **does not run**, and the filter forwards via `chain.doFilter`.
- With context path `/shop`, the request URI has prefix `/shop` while the pattern remains `/auth/login` relative to context path.

`authentication -> authentication` in the constructor is a **dummy authentication manager**, solely to provide a valid manager object for the fixture. It **does not** authenticate users. Never copy `CountingLoginFilter` or this dummy manager to production; real apps must use providers that genuinely verify credentials.

### 7.3. Running the Test and Expected Output

~~~bash
./mvnw test
~~~

Windows: `.\mvnw.cmd test`. With compatible JUnit 5/Surefire, all three tests pass; the summary line typically looks like:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
~~~

Exact output may vary by Maven Surefire version, but the key verification condition is **3 test methods pass**. This test does not execute real HTTP login, CSRF, `SecurityFilterChain` selection, or password providers. It isolates **gating logic**. Integration tests are still needed to prove the filter is registered and form actions point to the right endpoint.

## 8. When You Need a Composite Matcher

`RequestMatcher` can combine multiple criteria using implementations such as `AndRequestMatcher`, `OrRequestMatcher`, and `NegatedRequestMatcher`. Yet more complexity does not automatically mean greater security.

### 8.1. Restricting Method and Path

`PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST,"/auth/login")` already combines method + path, so never write:

~~~java
RequestMatcher wrong = request ->
    request.getRequestURI().contains("/login");
~~~

**Wrong:** `contains` could match `/admin/login-history`, `/evil/login123`, or unintended paths; additionally, using `requestURI` directly is error-prone around context paths, URI encoding, and servlet mappings.

### 8.2. Multiple Login Endpoints Genuinely Needing the Same Filter

If **the same auth mechanism** handles two distinct URLs, you can use:

~~~java
RequestMatcher loginEndpoints = new OrRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login"),
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login/legacy")
);

customFilter.setRequiresAuthenticationRequestMatcher(
    loginEndpoints
);
~~~

This is a **fragment** requiring imports for `OrRequestMatcher`, `PathPatternRequestMatcher`, `HttpMethod`, and `RequestMatcher` plus a custom filter with a well-defined parser. Before allowing two endpoints to accept passwords, confirm they share identical protections, rate limits, response contracts, and a deprecation plan for the legacy endpoint.

**Never widen a matcher to `/**`** just because an older login URL remains; that risks intercepting business requests by mistake.

### 8.3. Only REQUEST Dispatch If Required by the Flow

A custom filter using stateful login sometimes only wants initial `DispatcherType.REQUEST`, excluding `ERROR`/`FORWARD`. You can consider adding a dispatcher-type matcher and testing it:

~~~java
RequestMatcher loginOnlyOnRequest = new AndRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login"),
    new DispatcherTypeRequestMatcher(DispatcherType.REQUEST)
);
~~~

This fragment requires imports for `jakarta.servlet.DispatcherType`, `AndRequestMatcher`, `DispatcherTypeRequestMatcher`, and the path matcher. Be careful not to exclude `ASYNC`/`ERROR` if your mechanism relies on them; conversely, do not let a login filter re-read credentials on an error dispatch unintentionally.

## 9. Filter Ordering and Registration Pitfalls

### 9.1. Registering a Filter Twice

A custom class annotated with `@Component` (which Spring Boot may auto-register as a Servlet filter) and also added via `http.addFilterBefore(...)`/`addFilterAt(...)` can run **twice** or execute outside the intended security context. For custom auth filters, control instantiation, placement in `SecurityFilterChain`, and prevent unintended servlet-container registration.

If using `FilterRegistrationBean` to disable direct container registration for a filter added to a Spring Security chain, configure it on the exact bean instance. Never blindly copy an example mixing `@Component` and `addFilterBefore` without verifying execution count.

### 9.2. Placing the Filter in the Wrong Position

An authentication filter must run after `SecurityContextHolder` is prepared and before authorization evaluates the request. Placing it after `AuthorizationFilter` risks rejecting unauthenticated requests before the login filter runs. Misordering relative to `CsrfFilter`, session context filters, or exception translation can skip critical protections.

Position filters intentionally using `addFilterBefore`, `addFilterAfter`, or `addFilterAt`. `addFilterAt` does not necessarily "replace" an existing instance at that slot if both are registered; never attach a manual filter alongside `formLogin` assuming only one filter remains.

### 9.3. Two Filters Matching the Same Endpoint

If a custom JSON login filter and a form login filter both match `POST /login`, depending on order, the first filter may parse the body, return an error, redirect, or return before the second filter runs. Separate endpoints cleanly (e.g., `POST /api/auth/login` for JSON, `POST /login` for form) or design a single converter/handler supporting both formats under a tested contract.

## 10. CSRF, CORS, and HTTP Semantics

### 10.1. CSRF Is Not "Turned Off" by the Matcher

A POST form login can still require a CSRF token even when path and method match. Spring Security's `CsrfFilter` normally runs **before** the form login filter. When the token is missing or invalid, HTTP may return **403** without `attemptAuthentication` ever executing.

Thus a matcher test returning `true` and an HTTP request returning `403` **do not contradict each other**. Test layer by layer:

1. Matcher: do method and path match?
2. Filter chain: does the request enter the right chain?
3. CSRF: is the token valid?
4. Authentication: does the manager/provider authenticate?
5. Success handler/session: are response, cookie, and context stored properly?

For stateless APIs not relying on cookies, base CSRF decisions on your threat model rather than disabling it globally just for curl convenience. Browsers auto-sending credentials or cookies may still need CSRF protection.

### 10.2. CORS Preflight Is Not a Login Attempt

CORS preflight is normally an `OPTIONS` request sent before certain cross-origin requests. A `POST /auth/login` matcher does not trigger login on `OPTIONS`; CORS must be configured separately. If the server requires authentication on all `OPTIONS` requests before CORS runs, frontends will fail preflight. Never "fix" this by routing `OPTIONS` into the password authentication filter.

### 10.3. Use POST for Credential Submission

Never process passwords over GET because query strings can be captured in URL logs, browser history, and proxies. Use HTTPS, a form POST body, and a CSRF token where needed. A client intentionally sending POST to the right path without username/password is still **matched by the matcher**, yet the provider should reject it via the failure flow—never grant authentication merely because the URL matched.

## 11. Real-Project Test Matrix

When creating or customizing an authentication filter, build at least this matrix:

| Case | Should call `attemptAuthentication`? | Notes |
| --- | --- | --- |
| POST exact login path | Yes if request reaches filter past earlier layers | Test matcher and CSRF separately |
| GET login page | No | Displays form, does not log in |
| GET login processing path | No | May redirect/404 from another layer |
| OPTIONS login path | No | CORS preflight |
| POST login path with query | Yes | Query is not part of path |
| POST login path with extra segment | No if exact matcher | Avoid accidental `/**` matchers |
| POST other API endpoint | No | Let controllers/other filters handle |
| POST login under context path | Yes if builder configured compatibly | Test context/servlet mapping |
| POST login in chain lacking the filter | Cannot be called | Fix `securityMatcher`/chain order |
| POST login missing CSRF token | May be rejected before filter | Do not interpret as wrong password |
| POST login wrong password | Attempt runs, authentication fails | Handled by provider |
| POST login disabled account | Attempt runs, status failure | Do not bypass account-status checks |
| POST login valid password | Attempt runs, success flow | Valid session/context/redirect |
| `ERROR` dispatch to same URL | Per dispatcher policy | Do not trigger unintended login |
| Two filters both match | One or both depending on flow | Split URLs or define precedence |

### 11.1. Separating Unit Tests and Integration Tests

**Matcher/filter-gate unit tests** verify `attemptAuthentication` is invoked strictly when expected. They need no real passwords and no HTTP server.

**Filter-chain integration tests** verify `FilterChainProxy` picks the right chain, the login URL is inside the chain, CSRF rules, session authentication strategy, and success/failure handlers. Use Spring Security MockMvc test support to submit form logins with valid CSRF tokens. Never use "reached the controller" as proof a login filter worked: the filter normally handles the request **before the controller**.

**End-to-end tests** exercise browser/session cookies with form login and verify `GET /me` post-login, logout, CSRF, non-matching endpoints, real context paths, and reverse proxies if used in production.

## 12. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| POST login returns 404 | Login URL outside chain; filter not registered; wrong URL | Check `securityMatcher`, `loginProcessingUrl`, chain order |
| Login page renders but submit does not authenticate | Form action targets wrong URL/method; filter does not match | Compare form action with matcher; test method/path |
| POST login returns 403 despite right matcher | Missing/invalid CSRF or authorization policy | Inspect `CsrfFilter` and token before debugging passwords |
| GET login URL treated as login attempt | Matcher checks path only, ignoring method | Match `HttpMethod.POST` |
| Filter runs on every POST | Matcher too broad, checks method only | Match exact path + method |
| `/auth/login/extra` triggers login too | Using `/**` or overly permissive regex | Use exact pattern and negative tests |
| `GET /auth/login` redirects to `/login` | Filter skips attempt; authorization requires login | Normal depending on config, not necessarily a matcher bug |
| `POST /auth/login` wrong password has no failure handler | Custom filter lacks manager/handler/session policy | Use standard form login or configure completely |
| JSON login POST treated as missing credentials | Standard `UsernamePasswordAuthenticationFilter` reads form params | Use a proper JSON converter/filter design |
| Login endpoint under `/auth/**` with only `securityMatcher("/api/**")` | Chain does not include login URL | Move URL or widen chain matcher intentionally |
| Matcher test passes yet prod never runs filter | Filter missing from chain, wrong order, shadowed by another chain | Verify `FilterChainProxy` and registrations |
| Filter runs twice | Same instance auto-registered and added to chain | Register in one place only |
| Context path `/shop` breaks matcher | Confusing external URI with context-relative path | Use `PathPattern` matcher/`basePath` and test |
| OPTIONS fails with 401/403 before real request | Misconfigured CORS/preflight | Handle CORS before auth; never treat OPTIONS as login |
| User logs in cleanly yet `/me` stays anonymous | `SecurityContext` not saved / wrong session policy | Inspect success handler, repository, session/cookie |
| Two login filters fight over same URL | Overlapping matchers, unclear order | Separate processing URLs or unify auth flow |

### 12.1. Debug in Order So You Fix the Right Layer

1. Capture the **HTTP method**, path, context path, and servlet mapping actually seen by the server; never log passwords.
2. Check which chain `FilterChainProxy` selects.
3. Verify the filter instance is registered properly and not registered twice.
4. Test `RequestMatcher.matches(request)` against the real or corresponding mock request.
5. Check whether CSRF/CORS blocks the request before the filter.
6. If `attemptAuthentication` runs, check body parsing, `AuthenticationManager`, and providers.
7. If login succeeds yet subsequent requests are anonymous, debug `SecurityContext`/session persistence; do not change the matcher first.
8. If the request is authenticated yet returns `403`, check authorization rules and authorities.
9. Keep logs safe: never print credentials, raw session IDs, access/refresh tokens, or full authentication objects.

## 13. Scenarios and Answers

**Question 1.** The filter is added to the chain, yet `GET /login` does not call `attemptAuthentication`. Is this a bug?

**Answer:** No. For standard form login, GET renders the page while POST processes credentials. The filter may be invoked, yet its matcher returns false.

**Question 2.** A client sends `POST /auth/login` and the matcher returns true. Can we conclude the user is logged in?

**Answer:** No. The matcher only selects the authentication attempt. Manager/provider still must verify credentials and account conditions; CSRF may even block the request before the filter.

**Question 3.** An app uses `http.securityMatcher("/api/**")` and form login processing URL `/auth/login`. Why doesn't the filter run?

**Answer:** Because `/auth/login` never enters a chain matching only `/api/**`. Align the chain matcher and login endpoint; do not try fixing it with `permitAll()` alone.

**Question 4.** Does `authorizeHttpRequests().requestMatchers("/auth/login").permitAll()` guarantee `UsernamePasswordAuthenticationFilter` processes login?

**Answer:** No. It only sets an authorization rule; it does not ensure the filter is registered, the URL/method matcher matches, or the chain owns the endpoint.

**Question 5.** Should `requiresAuthenticationRequestMatcher` be set to `/**` so no requests are missed?

**Answer:** No. The authentication filter could hijack business requests. Match exact method/path and add negative tests.

**Question 6.** The client URL is `/shop/auth/login` when deployed with context path `/shop`. Which path should the matcher declare?

**Answer:** With a `PathPattern` matcher relative to context path, typically `/auth/login`. If the servlet has an extra mapping prefix, use `basePath` and test appropriately.

**Question 7.** `POST /auth/login` missing CSRF gets 403, while in the unit test the matcher returns true. Do these results contradict each other?

**Answer:** No. The unit test only checks the matcher; `CsrfFilter` can reject the request before the login filter is reached.

**Question 8.** A form sends a JSON body to standard `UsernamePasswordAuthenticationFilter` with no form params. Is a right matcher enough?

**Answer:** No. You need JSON parsing via an `AuthenticationConverter` or JSON-capable filter; the matcher only selects the request.

**Question 9.** In the unit test, `attemptAuthentication` returns null. Does that mean the login request succeeded?

**Answer:** No. That fixture demonstrates an incomplete flow. Production must return a manager-verified authentication, throw an exception, or continue per contract.

**Question 10.** A custom filter is annotated with `@Component` and added via `addFilterBefore`. What can happen?

**Answer:** The filter may be registered twice (once by the container and once in the Spring Security chain). Ensure registration happens in one place only.

**Question 11.** Why doesn't a non-matching `GET /auth/login` necessarily return HTTP 405?

**Answer:** The filter simply forwards the request; afterwards, authorization/entry points, controller mappings, or a fallback chain may redirect or return 404/405 depending on config. The matcher does not dictate response status when skipping a request.

**Question 12.** What should you do if two different login URLs need the same provider?

**Answer:** Consider an `OrRequestMatcher` of two **exact POST paths**, while standardizing parsers, policies, CSRF, rate limits, success/failure handlers, and avoiding matcher overlap with other filters.

## 14. Integration Checklist

- [ ] Identify the exact `SecurityFilterChain` holding the authentication filter for the login endpoint.
- [ ] Clearly distinguish `securityMatcher`, `authorizeHttpRequests.requestMatchers`, and `requiresAuthenticationRequestMatcher`.
- [ ] For standard form login, prefer `formLogin(...loginProcessingUrl(...))` over manual filter instantiation.
- [ ] For custom filters, set `RequestMatcher` via constructor or `setRequiresAuthenticationRequestMatcher` on the right instance without accidentally overwriting it via `setFilterProcessesUrl`.
- [ ] Restrict the matcher to exact **HTTP method** and **exact path**, never `contains("/login")` or overly broad wildcards.
- [ ] Test GET/POST/PUT/OPTIONS, wrong paths, extra slashes/segments, query strings, context paths, and servlet mappings.
- [ ] Never confuse matcher `true` with authentication success, authorization permit, or valid CSRF.
- [ ] Form/JSON parsers enforce content type, username/password parameter names, and body size limits.
- [ ] Browser login POST includes a valid CSRF token and runs over HTTPS.
- [ ] Custom filters have proper manager/provider, handlers, context repository, session strategy, rate limits, auditing, and filter ordering.
- [ ] Never create an authenticated token from client input without verification.
- [ ] Never register the same filter twice; know every filter running in the selected chain.
- [ ] In multi-chain setups, ensure the login endpoint is not excluded by `securityMatcher`; include a catch-all chain protecting the whole app.
- [ ] Distinguish 404/405/403/401/302 errors coming from different layers instead of "fixing" them by widening matchers recklessly.
- [ ] Run both filter-gate unit tests and chain + CSRF + login success/failure integration tests with real dependencies.

**Conclusion:** `requiresAuthenticationRequestMatcher` is the **gate deciding whether an authentication filter attempts authentication on the current request**. The standard form-login configuration is **`POST` to a specific processing URL**. The matcher only scopes the filter's responsibility: it does not select security chains, grant permissions, check passwords, or replace CSRF. For safe integration, align URL/method between client and filter, place the filter in the right chain, and test both requests that should be processed and requests that must pass through.

## Official References

- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Java Configuration: SecurityFilterChain Endpoints](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — PathPatternRequestMatcher.Builder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html)
- [Spring Security 6.5 — RequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security 6.5 — Servlet Security Filters](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
